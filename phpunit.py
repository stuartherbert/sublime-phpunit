import datetime
import functools
import os
import re
import subprocess
import time
import thread
import sublime
import sublime_plugin

# the AsyncProcess class has been cribbed from:
# https://github.com/maltize/sublime-text-2-ruby-tests/blob/master/run_ruby_test.py


class AsyncProcess(object):
    def __init__(self, cmd, listener):
        self.cmd = cmd
        self.listener = listener
        print "DEBUG_EXEC: " + self.cmd
        self.proc = subprocess.Popen([self.cmd], shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if self.proc.stdout:
            thread.start_new_thread(self.read_stdout, ())
        if self.proc.stderr:
            thread.start_new_thread(self.read_stderr, ())

    def read_stdout(self):
        while True:
            data = os.read(self.proc.stdout.fileno(), 2 ** 15)
            if data != "":
                sublime.set_timeout(functools.partial(self.listener.append_data, self.proc, data), 0)
            else:
                self.proc.stdout.close()
                self.listener.is_running = False
                self.listener.append_data(self.proc, "\n--- PROCESS COMPLETE ---")
                break

    def read_stderr(self):
        while True:
            data = os.read(self.proc.stderr.fileno(), 2 ** 15)
            if data != "":
                sublime.set_timeout(functools.partial(self.listener.append_data, self.proc, data), 0)
            else:
                self.proc.stderr.close()
                self.listener.is_running = False
                break

# the StatusProcess class has been cribbed from:
# https://github.com/maltize/sublime-text-2-ruby-tests/blob/master/run_ruby_test.py


class StatusProcess(object):
    def __init__(self, msg, listener):
        self.msg = msg
        self.listener = listener
        thread.start_new_thread(self.run_thread, ())

    def run_thread(self):
        progress = ""
        while True:
            if self.listener.is_running:
                if len(progress) >= 10:
                    progress = ""
                progress += "."
                sublime.set_timeout(functools.partial(self.listener.update_status, self.msg, progress), 0)
                time.sleep(1)
            else:
                break


class OutputView(object):
    def __init__(self, name, window):
        self.output_name = name
        self.window = window

    def show_output(self):
        self.ensure_output_view()
        self.window.run_command("show_panel", {"panel": "output." + self.output_name})

    def show_empty_output(self):
        self.ensure_output_view()
        self.clear_output_view()
        self.show_output()

    def ensure_output_view(self):
        if not hasattr(self, 'output_view'):
            self.output_view = self.window.get_output_panel(self.output_name)

    def clear_output_view(self):
        self.ensure_output_view()
        self.output_view.set_read_only(False)
        edit = self.output_view.begin_edit()
        self.output_view.erase(edit, sublime.Region(0, self.output_view.size()))
        self.output_view.end_edit(edit)
        self.output_view.set_read_only(True)

    def append_data(self, proc, data):
        str = data.decode("utf-8")
        str = str.replace('\r\n', '\n').replace('\r', '\n')

        selection_was_at_end = (len(self.output_view.sel()) == 1
          and self.output_view.sel()[0]
            == sublime.Region(self.output_view.size()))
        self.output_view.set_read_only(False)
        edit = self.output_view.begin_edit()
        self.output_view.insert(edit, self.output_view.size(), str)
        if selection_was_at_end:
            self.output_view.show(self.output_view.size())
        self.output_view.end_edit(edit)
        self.output_view.set_read_only(True)


class CommandBase:
    def __init__(self, window):
        self.window = window
        # Load the settings files
        self.settings_file = '%s.sublime-settings' % __name__
        self.settings = sublime.load_settings(self.settings_file)
        self.additional_args = self.settings.get('additional_args', {})

    def show_output(self):
        if not hasattr(self, 'output_view'):
            self.output_view = OutputView('phpunit', self.window)

        self.output_view.show_output()

    def show_empty_output(self):
        if not hasattr(self, 'output_view'):
            self.output_view = OutputView('phpunit', self.window)

        self.output_view.clear_output_view()
        self.output_view.show_output()

    def start_async(self, caption, executable):
        self.is_running = True
        self.proc = AsyncProcess(executable, self)
        StatusProcess(caption, self)

    def append_data(self, proc, data):
        self.output_view.append_data(proc, data)

    def update_status(self, msg, progress):
        sublime.status_message(msg + " " + progress)


class PhpunitCommand(CommandBase):
    def run(self, path, testfile='', classname=''):
        self.show_empty_output()

        cmd = "cd '" + path[0] + "' && phpunit"

        # Add the additional arguments from the settings file to the command
        for key, value in self.additional_args.items():
            cmd = cmd + " " + key
            if value != "":
                cmd = cmd + "=" + value

        if len(path) > 0:
            cmd = cmd + " -c '" + path[1] + "' "
        if testfile != '':
            cmd = cmd + " '" + testfile + "'"
        if classname != '':
            cmd = cmd + " '" + classname + "'"

        self.append_data(self, "$ " + cmd + "\n")
        self.start_async("Running PHPUnit", cmd)


class ActiveFile:
    searched_folders = {}
    search_results_cache = {}
    last_search_time = None

    def is_test_buffer(self):
        filename = os.path.splitext(os.path.basename(self.file_name()))[0]
        if filename.endswith('Test'):
            return True
        return False

    def is_phpunitxml(self):
        # is this a phpunit.xml file?
        filename = os.path.basename(self.file_name())
        if filename == 'phpunit.xml' or filename == 'phpunit.xml.dist':
            return True
        return False

    def determineClassToTest(self):
        class_to_test = os.path.splitext(os.path.basename(self.file_name()))[0]
        if not class_to_test.endswith('Test'):
            class_to_test = class_to_test + "Test"

        return class_to_test

    def determineTestFile(self):
        filename = os.path.splitext(os.path.basename(self.file_name()))[0]
        if filename.endswith('Test'):
            return self.file_name()

        return None

    def findPhpunitXml(self, folders={}):
        dir_name = os.path.dirname(self.file_name())

        files_to_find = ['phpunit.xml', 'phpunit.xml.dist']
        for file_to_find in files_to_find:
            result = self.findFileFor(folders, dir_name, file_to_find)
            if result is not None:
                return [os.path.dirname(result), os.path.basename(result)]
        return None

    def expireSearchResultsCache(self):
        now = datetime.datetime.now()
        if ActiveFile.last_search_time is not None:
            since = ActiveFile.last_search_time + datetime.timedelta(seconds=2)
        if ActiveFile.last_search_time is None or now > since:
            ActiveFile.last_search_time = now
            ActiveFile.search_results_cache = {}

    def reachedTopLevelFolder(self, folders, oldpath, path):
        if oldpath == path:
            return True
        for folder in folders:
            if path == folder:
                return True
        return False

    def findFolderContainingFile(self, folders, oldpath, path, filename):
        if self.reachedTopLevelFolder(folders, oldpath, path):
            return None
        if os.path.exists(os.path.join(path, filename)):
            return [path, filename]

        return self.findFolderContainingFile(folders, path, os.path.dirname(path), filename)

    def findFileFor(self, folders, path, suffix):
        self.expireSearchResultsCache()
        ActiveFile.searched_folders = {}
        print "------------------------ SEARCH STARTS HERE ---------------------"

        if suffix in ActiveFile.search_results_cache:
            return ActiveFile.search_results_cache[suffix]

        path = self._findFileFor(folders, '', path, suffix, 3)
        ActiveFile.search_results_cache[suffix] = path
        return path

    def _findFileFor(self, folders, oldpath, path, suffix, depth):
        if len(folders) == 0 and depth == 0:
            return None
        if self.reachedTopLevelFolder(folders, oldpath, path):
            return None
        # optimisation - avoid looking in the same place twice
        filenameToTest = os.path.join(path, suffix)
        print "Looking for " + filenameToTest
        if os.path.exists(filenameToTest):
            return filenameToTest
        found_path = self.searchSubfoldersFor(path, suffix)
        if found_path is not None:
            return found_path
        depth = depth - 1
        return self._findFileFor(folders, path, os.path.dirname(path), suffix, depth)

    def searchSubfoldersFor(self, path, suffix):
        print "searchSubfoldersFor: " + path + ' ' + suffix

        for root, dirs, names in os.walk(path):
            for subdir in dirs:
                print "looking at dir " + subdir
                # optimisation - avoid looking in hidden places
                if subdir[0] == '.':
                    # print "skipping hidden folder " + subdir
                    continue
                # optimisation - avoid looking in the same place twice
                pathToSearch = os.path.join(path, subdir)
                if pathToSearch in ActiveFile.searched_folders:
                    print "Skipping " + pathToSearch
                    continue
                ActiveFile.searched_folders[pathToSearch] = True
                # if we get here, we have not discarded this folder yet
                filenameToTest = os.path.join(pathToSearch, suffix)
                print "Looking in subfolders for " + filenameToTest
                if os.path.exists(filenameToTest):
                    print "Found " + filenameToTest
                    return filenameToTest
                found_path = self.searchSubfoldersFor(pathToSearch, suffix)
                if found_path is not None:
                    print "Found path!!"
                    return found_path
                print "Run out of options"
        return None

    def cannot_find_xml(self):
        sublime.status_message("Cannot find phpunit.xml or phpunit.xml.dist file")

    def xml_file_needed(self):
        return "You need a phpunit.xml or phpunit.xml.dist file to use PHPUnit"


class ActiveView(ActiveFile):
    def is_php_buffer(self):
        # is this a PHP buffer?
        if re.search('.+\PHP.tmLanguage', self.view.settings().get('syntax')):
            return True
        return False

    def file_name(self):
        return self.view.file_name()

    def find_tested_file(self):
        classname = self.determine_full_class_name()
        path_to_search = self.file_name().replace('/' + classname + '.php', '')
        if classname[-4:] == 'Test':
            classname = classname[:-4]
        classname = classname + '.php'
        path = self.findFileFor(self.view.window().folders(), path_to_search, classname)
        if path is None:
            return None

        return [path, classname]

    def find_test_file(self):
        classname = self.determine_full_class_name()
        path_to_search = self.file_name().replace('/' + classname + '.php', '')
        path = self.findFileFor(self.view.window().folders(), path_to_search, classname + 'Test.php')
        if path is None:
            return None

        return [path, classname]

    def determine_full_class_name(self):
        namespace = self.extract_namespace()
        classname = self.extract_classname()
        path = ''
        if len(namespace) > 0:
            namespace = namespace.replace('\\', '/')
            path = path + namespace + '/'
        classname = classname.replace('_', '/')
        path = path + classname
        return path

    def extract_namespace(self):
        namespaces = self.view.find_all("^namespace ([A-Za-z0-9_\\\]+);")
        if namespaces is None or len(namespaces) == 0:
            return ''
        for namespace in namespaces:
            line = self.view.substr(namespace)
            return line[10:-1]

    def extract_classname(self):
        classes = self.view.find_all("^class [A-Za-z0-9_]+")
        if classes is None or len(classes) == 0:
            return None
        for classname in classes:
            line = self.view.substr(classname)
            return line[6:]


class ActiveWindow(ActiveFile):
    def file_name(self):
        if hasattr(self, '_file_name'):
            return self._file_name

        return None

    def determine_filename(self, args=[]):
        if len(args) == 0:
            active_view = self.window.active_view()
            filename = active_view.file_name()
        else:
            filename = args[0]

        self._file_name = filename

    def is_php_buffer(self):
        ext = os.path.splitext(self.file_name())[1]
        if ext == 'php':
            return True
        return False


class PhpunitTextBase(sublime_plugin.TextCommand, ActiveView):
    def run(self, args):
        print 'Not implemented'


class PhpunitTestThisClass(PhpunitTextBase):
    def run(self, args):
        path = self.findPhpunitXml(self.view.window().folders())
        if path is None:
            self.cannot_find_xml()
            return

        file_to_test = self.find_test_file()
        if file_to_test is None:
            self.cannot_find_test_file()
            return

        cmd = PhpunitCommand(self.view.window())
        cmd.run(path, file_to_test[0], file_to_test[1])

    def description(self):
        return 'Test This Class...'

    def is_enabled(self):
        if not self.is_php_buffer():
            return False
        if self.is_test_buffer():
            return False
        path = self.findPhpunitXml(self.view.window().folders())
        if path is None:
            return False
        path = self.find_test_file()
        if path is None:
            return False
        return True

    def is_visible(self):
        if not self.is_php_buffer():
            return False
        if self.is_test_buffer():
            return False
        path = self.findPhpunitXml(self.view.window().folders())
        if path is None:
            return False
        return True


class PhpunitOpenTestClass(PhpunitTextBase):
    def run(self, args):
        file_to_open = self.find_test_file()
        if file_to_open is None:
            self.cannot_find_test_file()
            return

        self.view.window().open_file(file_to_open[0])

    def description(self):
        return 'Open Test Class'

    def is_enabled(self):
        if not self.is_php_buffer():
            return False
        if self.is_test_buffer():
            return False
        path = self.find_test_file()
        if path is None:
            return False
        return True

    def is_visible(self):
        if not self.is_php_buffer():
            return False
        if self.is_test_buffer():
            return False
        return True


class PhpunitOpenClassBeingTested(PhpunitTextBase):
    def run(self, args):
        file_to_open = self.find_tested_file()
        if file_to_open is None:
            self.cannot_find_tested_file()
            return

        self.view.window().open_file(file_to_open[0])

    def description(self):
        return 'Open Class Being Tested'

    def is_enabled(self):
        if not self.is_php_buffer():
            return False
        if not self.is_test_buffer():
            return False
        path = self.find_tested_file()
        if path is None:
            return False
        return True

    def is_visible(self):
        if not self.is_php_buffer():
            return False
        if not self.is_test_buffer():
            return False
        return True


class PhpunitRunThisPhpunitXmlCommand(PhpunitTextBase):
    def run(self, args):
        phpunit_xml_file = self.file_name()
        dir_to_cd = os.path.dirname(phpunit_xml_file)
        cmd = PhpunitCommand(self.view.window())
        cmd.run([dir_to_cd, os.path.basename(phpunit_xml_file)])

    def is_enabled(self):
        return self.is_visible()

    def is_visible(self):
        return self.is_phpunitxml()

    def description(self, paths=[]):
        return 'Run Using This XML File...'


class PhpunitRunTheseTestsCommand(PhpunitTextBase):
    def run(self, args):
        path = self.findPhpunitXml(self.view.window().folders())
        if path is None:
            self.cannot_find_xml()
            return

        print path
        file_to_test = self.determineTestFile()
        cmd = PhpunitCommand(self.view.window())
        cmd.run(path, file_to_test)

    def description(self):
        return 'Run These Tests...'

    def is_enabled(self):
        if not self.is_php_buffer():
            return False
        if not self.is_test_buffer():
            return False
        path = self.findPhpunitXml(self.view.window().folders())
        if path is None:
            return False
        return True

    def is_visible(self):
        return self.is_enabled()


class PhpunitRunAllTestsCommand(PhpunitTextBase):
    def run(self, args):
        path = self.findPhpunitXml(self.view.window().folders())
        if path is None:
            self.cannot_find_xml()
            return
        cmd = PhpunitCommand(self.view.window())
        cmd.run(path)

    def description(self):
        return 'Run All Unit Tests...'

    def is_enabled(self):
        if not self.is_php_buffer():
            return False
        if self.is_phpunitxml():
            return False
        path = self.findPhpunitXml(self.view.window().folders())
        if path is None:
            return False
        return True

    def is_visible(self):
        return self.is_enabled()


class PhpunitNotAvailableCommand(PhpunitTextBase):
    def is_visible(self):
        if self.is_php_buffer():
            return False
        if self.is_phpunitxml():
            return False
        return True

    def is_enabled(self):
        return False

    def description(self):
        return self.xml_file_needed()


class PhpunitWindowBase(sublime_plugin.WindowCommand, ActiveWindow):
    def run(self, paths=[]):
        print "not implemented"


class RunPhpunitOnXmlCommand(PhpunitWindowBase):
    def run(self, paths=[]):
        self.determine_filename(paths)
        filename = self.file_name()
        dir_to_cd = os.path.dirname(filename)
        cmd = PhpunitCommand(self.window)
        cmd.run([dir_to_cd, os.path.basename(filename)])

    def is_enabled(self, paths=[]):
        return self.is_visible(paths)

    def is_visible(self, paths=[]):
        self.determine_filename(paths)
        return self.is_phpunitxml()

    def description(self, paths=[]):
        return 'Run Using This XML File...'


class RunPhpunitOnTheseTestsCommand(PhpunitWindowBase):
    def run(self, paths=[]):
        self.determine_filename(paths)
        path = self.findPhpunitXml()
        if path is None:
            self.cannot_find_xml()
            return

        file_to_test = self.determineTestFile()
        cmd = PhpunitCommand(self.window.active_view().window())
        cmd.run(path, file_to_test)

    def is_enabled(self, paths=[]):
        return self.is_visible(paths)

    def is_visible(self, paths=[]):
        self.determine_filename(paths)
        if not self.is_test_buffer():
            return False
        path = self.findPhpunitXml()
        if path is None:
            return False
        return True

    def description(self, paths=[]):
        return 'Run These Tests...'


class RunPhpunitTestsCommand(PhpunitWindowBase):
    def run(self, paths=[]):
        self.determine_filename(paths)
        path = self.findPhpunitXml()
        if path is None:
            self.cannot_find_xml()
            return

        cmd = PhpunitCommand(self.window)
        cmd.run(path)

    def is_enabled(self, paths=[]):
        return self.is_visible(paths)

    def is_visible(self, paths=[]):
        self.determine_filename(paths)
        if self.is_phpunitxml():
            return False
        path = self.findPhpunitXml()
        if path is None:
            return False
        return True

    def description(self, paths=[]):
        return 'Run All PHPUnit Tests...'


class CannotRunPhpunitCommand(PhpunitWindowBase):
    def is_visible(self, paths=[]):
        self.determine_filename(paths)
        path = self.findPhpunitXml()
        if path is not None:
            return False
        return True

    def is_enabled(self):
        return False

    def description(self):
        return self.xml_file_needed()
