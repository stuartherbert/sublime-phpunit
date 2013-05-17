import datetime
import functools
import os
import re
import subprocess
import time
import thread
import sublime
import sublime_plugin


class Prefs:
    @staticmethod
    def load():
        settings = sublime.load_settings('PHPUnit.sublime-settings')
        Prefs.folder_search_hints = settings.get('top_folder_hints', [])
        Prefs.folder_exclusions = settings.get('folder_exclusions', [])
        Prefs.max_search_secs = settings.get('max_search_secs', 2)
        Prefs.phpunit_xml_location_hints = settings.get('phpunit_xml_location_hints', [])
        Prefs.phpunit_additional_args = settings.get('phpunit_additional_args', {})
        Prefs.debug = settings.get('debug', 0)
        Prefs.path_to_phpunit = settings.get('path_to_phpunit', False)
        Prefs.copy_env = settings.get('copy_env', True)
        Prefs.override_env = settings.get('override_env', {})

Prefs.load()


class Msgs:
    operation = 'top-level'

    @staticmethod
    def debug_msg(msg):
        if Prefs.debug == 1:
            print "[PHPUnit Plugin " + Msgs.operation + "()] " + msg

Msgs.debug_msg('')
Msgs.debug_msg('')
Msgs.debug_msg('')
Msgs.debug_msg('=========================================================')
Msgs.debug_msg('PHPUnit Plugin Reloaded')
Msgs.debug_msg('---------------------------------------------------------')
Msgs.debug_msg('')
Msgs.debug_msg('')
Msgs.debug_msg('')

# the AsyncProcess class has been cribbed from:
# https://github.com/maltize/sublime-text-2-ruby-tests/blob/master/run_ruby_test.py


class AsyncProcess(object):
    def __init__(self, cmd, cwd, listener):
        self.listener = listener
        if Prefs.copy_env:
            env = os.environ.copy()

            # add 'PWD' to the environment, for those folks who use it
            # in their tests
            # env['PWD'] = cwd
        else:
            Msgs.debug_msg("Using EMPTY environment!")
            env = {}

        if Prefs.override_env:
            Msgs.debug_msg("Updating environment with " + ' '.join(Prefs.override_env))
            env.update(Prefs.override_env)

        Msgs.debug_msg("DEBUG_EXEC: " + ' '.join(cmd))

        if os.name == 'nt':
            # we have to run PHPUnit via the shell to get it to work for everyone on Windows
            # no idea why :(
            # I'm sure this will prove to be a terrible idea
            self.proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=env)
        else:
            # Popen works properly on OSX and Linux
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=env)
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
                break

    def read_stderr(self):
        while True:
            data = os.read(self.proc.stderr.fileno(), 2 ** 15)
            if data != "":
                sublime.set_timeout(functools.partial(self.listener.append_data, self.proc, data), 0)
            else:
                self.proc.stderr.close()
                self.listener.is_running = False
                sublime.set_timeout(functools.partial(self.listener.append_data, self.proc, "\n--- PROCESS COMPLETE ---"), 0)
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
        str = re.sub('(.*)(\[2K|;\d+m)', '', str)
        str = re.sub('\[(\d+)m', '', str)

        # selection_was_at_end = (len(self.output_view.sel()) == 1
        #  and self.output_view.sel()[0]
        #    == sublime.Region(self.output_view.size()))
        self.output_view.set_read_only(False)
        edit = self.output_view.begin_edit()
        self.output_view.insert(edit, self.output_view.size(), str)
        #if selection_was_at_end:
        self.output_view.show(self.output_view.size())
        self.output_view.end_edit(edit)
        self.output_view.set_read_only(True)


class CommandBase:
    def __init__(self, window):
        self.window = window

    def show_output(self):
        if not hasattr(self, 'output_view'):
            self.output_view = OutputView('phpunit', self.window)

        self.output_view.show_output()

    def show_empty_output(self):
        if not hasattr(self, 'output_view'):
            self.output_view = OutputView('phpunit', self.window)

        self.output_view.clear_output_view()
        self.output_view.show_output()

    def start_async(self, caption, executable, cwd):
        self.is_running = True
        self.proc = AsyncProcess(executable, cwd, self)
        StatusProcess(caption, self)

    def append_data(self, proc, data):
        self.output_view.append_data(proc, data)

    def update_status(self, msg, progress):
        sublime.status_message(msg + " " + progress)


class PhpunitCommand(CommandBase):
    def run(self, configfile, testfile='', classname=''):
        self.show_empty_output()

        if Prefs.path_to_phpunit is not False:
            args = [Prefs.path_to_phpunit]
        else:
            # find where PHPUnit is installed
            args = ["phpunit"]

        # Add the additional arguments from the settings file to the command
        for key, value in Prefs.phpunit_additional_args.items():
            arg = key
            if value != "":
                arg += "=" + value
            args.append(arg)

        if os.path.isfile(configfile) > 0:
            args.append("-c")
            args.append(os.path.basename(configfile))
        if classname != '':
            args.append(classname)
        if testfile != '':
            args.append(testfile)

        if os.path.isdir(configfile):
            folder = configfile
        else:
            folder = os.path.dirname(configfile)

        self.append_data(self, "# Running in folder: " + folder + "\n")
        self.append_data(self, "$ " + ' '.join(args) + "\n")
        self.start_async("Running PHPUnit", args, folder)


class FoundFiles:
    cache = {}

    @staticmethod
    def addToCache(top_folder, filename, result):
        if top_folder not in FoundFiles.cache:
            FoundFiles.cache[top_folder] = {}
        Msgs.debug_msg('Adding ' + result + ' to cache for ' + top_folder)
        FoundFiles.cache[top_folder][filename] = result

    @staticmethod
    def removeFromCache(top_folder, filename):
        Msgs.debug_msg('Removing ' + filename + ' from cache for ' + top_folder)
        if top_folder not in FoundFiles.cache:
            Msgs.debug_msg('-- no cache for ' + top_folder)
            return

        if filename not in FoundFiles.cache[top_folder]:
            Msgs.debug_msg('-- ' + filename + ' not found in cache')
            return

        del FoundFiles.cache[top_folder][filename]
        Msgs.debug_msg('-- ' + filename + ' removed from cache')

    @staticmethod
    def removeCacheFor(top_folder):
        Msgs.debug_msg('Removing cache for ' + top_folder)
        if top_folder not in FoundFiles.cache:
            Msgs.debug_msg('-- no cache for ' + top_folder)
            return
        del FoundFiles.cache[top_folder]
        Msgs.debug_msg('-- removed cache')

    @staticmethod
    def removeCache():
        Msgs.debug_msg('Completely emptying the cache')
        FoundFiles.cache = {}

    @staticmethod
    def getFromCache(top_folder, filename):
        Msgs.debug_msg('Get ' + filename + ' from cache for ' + top_folder)
        if top_folder not in FoundFiles.cache:
            Msgs.debug_msg('-- no cache for ' + top_folder)
            return None

        if filename not in FoundFiles.cache[top_folder]:
            Msgs.debug_msg('-- ' + filename + ' not found in cache')
            return None

        Msgs.debug_msg('-- found ' + FoundFiles.cache[top_folder][filename])
        return FoundFiles.cache[top_folder][filename]


class FindFiles:
    searched_folders = {}
    searched_for = {}
    last_search_time = None

    @staticmethod
    def find(top_folder, search_from, files_to_find):
        for file_to_find in files_to_find:
            Msgs.debug_msg("Looking for " + file_to_find)
            # check the cache - do we already know the answer?
            result = FindFiles.searchCacheFor(top_folder, file_to_find)
            if result is not None:
                return result

            # check the top folder
            result = FindFiles.searchTopFolderFor(top_folder, file_to_find)
            if result is not None:
                # cache the result
                FoundFiles.addToCache(top_folder, file_to_find, result)
                return result

            # check in the places given in hints
            result = FindFiles.searchNamedPlacesFor(top_folder, Prefs.phpunit_xml_location_hints, file_to_find)
            if result is not None:
                # cache the result
                FoundFiles.addToCache(top_folder, file_to_find, result)
                return result

            # if we reach this point, we are going to have to search on disk
            dir_name = search_from
            if not os.path.isdir(dir_name):
                dir_name = os.path.dirname(dir_name)

            # straight-line search - fastest for most people
            result = FindFiles.searchStraightUpwardsFor(top_folder, dir_name, file_to_find)
            if result is not None:
                # cache the result
                FoundFiles.addToCache(top_folder, file_to_find, result)
                return result

            # okay, so where is it?
            result = ProjectFiles.find(top_folder, file_to_find)
            if result is not None:
                FoundFiles.addToCache(top_folder, file_to_find, result)
                return result

        # if we get here, we cannot find the file
        return None

    @staticmethod
    def searchCacheFor(top_folder, file_to_find):
        return FoundFiles.getFromCache(top_folder, file_to_find)

    @staticmethod
    def searchNamedPlacesFor(top_folder, places, file_to_find):
        for place in places:
            pathToTest = os.path.join(top_folder, place)
            filenameToTest = os.path.join(pathToTest, file_to_find)
            Msgs.debug_msg('Searching for file ' + filenameToTest)
            if os.path.exists(filenameToTest):
                return filenameToTest
        return None

    @staticmethod
    def searchTopFolderFor(top_folder, file_to_find):
        Msgs.debug_msg('Searching top folder ' + top_folder + ' for ' + file_to_find)
        return FindFiles.searchFolderFor(top_folder, file_to_find)

    @staticmethod
    def searchFolderFor(folder, file_to_find):
        Msgs.debug_msg('-- Searching ' + folder + ' for ' + file_to_find)
        filenameToTest = os.path.join(folder, file_to_find)
        if os.path.exists(filenameToTest):
            Msgs.debug_msg('---- Found ' + filenameToTest)
            return filenameToTest
        return None

    @staticmethod
    def reachedTopLevelFolders(oldpath, path):
        if oldpath == path:
            return True
        hints = Prefs.folder_search_hints
        for hint in hints:
            if os.path.exists(os.path.join(path, hint)):
                return True
        return False

    @staticmethod
    def reachedTopLevelFolder(folder, oldpath, path):
        if oldpath == path:
            return True
        if folder[:len(path)] == path:
            return True
        return False

    @staticmethod
    def searchStraightUpwardsFor(top_folder, path, file_to_find):
        Msgs.debug_msg("---- New search straight upwards ----")

        # do we know where these files are?
        return FindFiles._searchStraightUpwardsFor(top_folder, '', path, file_to_find)

    @staticmethod
    def _searchStraightUpwardsFor(top_folder, oldpath, path, file_to_find):
        Msgs.debug_msg("Looking in " + path)
        filenameToTest = os.path.join(path, file_to_find)
        Msgs.debug_msg("Looking for " + filenameToTest)
        if os.path.exists(filenameToTest):
            return filenameToTest

        if FindFiles.reachedTopLevelFolder(top_folder, oldpath, path):
            return None

        return FindFiles._searchStraightUpwardsFor(top_folder, path, os.path.dirname(path), file_to_find)


class ProjectFiles:
    files = {}
    last_built_time = None

    @staticmethod
    def buildFilesList(path):
        Msgs.debug_msg('Building list of files under ' + path)
        # does the path exist?
        if not os.path.exists(path):
            return None

        ProjectFiles.files[path] = []

        # how long will this take? let's find out
        start = datetime.datetime.now()

        # we're going to build up a cache of the files inside this project
        i = 0
        for root, dirs, files in os.walk(path):
            for name in files:
                ProjectFiles.files[path].append(os.path.join(root, name))
                i = i + 1

        end = datetime.datetime.now()
        duration = (end - start)
        Msgs.debug_msg('-- took ' + str(duration.seconds) + '.' + str(duration.microseconds) + ' second(s) to build')
        Msgs.debug_msg('-- found ' + str(i) + ' file(s)')
        # print ProjectFiles.files[path]
        ProjectFiles.last_built_time = end

    @staticmethod
    def find(top_folder, filename):
        Msgs.debug_msg('Searching ProjectFiles cache for ' + filename)
        if top_folder not in ProjectFiles.files:
            Msgs.debug_msg('-- no cache for ' + top_folder)
            return None

        result = [x for x in ProjectFiles.files[top_folder] if filename in x]
        if len(result) == 0:
            Msgs.debug_msg('-- none found')
            return None
        Msgs.debug_msg('-- found ' + result[0])
        return result[0]

    @staticmethod
    def expired(when):
        if when < ProjectFiles.last_built_time:
            return True
        return False


class ActiveFile:
    def is_test_buffer(self):
        Msgs.debug_msg('Is buffer a file containing tests?')
        filename = self.file_name()
        if not os.path.isfile(filename):
            Msgs.debug_msg("-- Buffer is not a real file; unsaved new buffer?")
            return False
        filename = os.path.splitext(filename)[0]
        if filename.endswith('Test'):
            Msgs.debug_msg("-- Buffer is a test file")
            return True
        Msgs.debug_msg("-- Buffer is not a test file")
        return False

    def is_tests_buffer(self):
        Msgs.debug_msg('Is buffer a file containing a testsuite?')
        filename = self.file_name()
        if not os.path.isfile(filename):
            Msgs.debug_msg("-- Buffer is not a real file; unsaved new buffer?")
            return False
        filename = os.path.splitext(filename)[0]
        if filename.endswith('Tests'):
            Msgs.debug_msg("Buffer is a testsuite file")
            return True
        Msgs.debug_msg("Buffer is not a testsuite file")
        return False

    def is_phpunitxml(self):
        # is this a phpunit.xml file?
        filename = self.file_name()
        if not os.path.isfile(filename):
            Msgs.debug_msg("Buffer is not phpunit.xml; is not a real file")
            return False
        filename = os.path.basename(filename)
        if filename == 'phpunit.xml' or filename == 'phpunit.xml.dist':
            Msgs.debug_msg("Buffer is a phpunit.xml file")
            return True
        Msgs.debug_msg("Buffer is not a phpunit.xml file")
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

    def findPhpunitXml(self, search_from):
        Msgs.debug_msg("Looking for phpunit.xml of some kind")

        # what are we looking for?
        files_to_find = ['phpunit.xml', 'phpunit.xml.dist']

        return FindFiles.find(self.top_folder(), search_from, files_to_find)

    def error_message(self, message):
        sublime.status_message(message)

    def cannot_find_xml(self):
        return "Cannot find phpunit.xml or phpunit.xml.dist file"

    def cannot_find_test_file(self):
        return "Cannot find file containing unit tests"

    def cannot_find_tested_file(self):
        return "Cannot find file to be tested"

    def not_in_project(self):
        return "Only works if you have a ST2 project open"

    def not_php_file(self, syntax):
        Msgs.debug_msg(syntax)
        matches = re.search("/([^/]+).tmLanguage", syntax)
        if matches is not None:
            syntax = matches.group(1)
        return "Plugin does not support " + syntax + " syntax buffers"


class ActiveView(ActiveFile):
    def is_php_buffer(self):
        # most reliable way is to check the file extension
        # we cannot rely on the buffer syntax; it can sometimes report
        # 'HTML' even in a PHP buffer
        ext = os.path.splitext(self.file_name())[1]
        if ext == '.php':
            Msgs.debug_msg("Buffer is a PHP buffer")
            return True
        # is this a PHP buffer?
        if re.search('.+\PHP.tmLanguage', self.view.settings().get('syntax')):
            return True
        # if we get here, we're not sure what else to try
        Msgs.debug_msg("Buffer is not a PHP buffer; extension is: " + ext + "; syntax is: " + self.view.settings().get('syntax'))
        return False

    def has_project_open(self):
        folders = self.view.window().folders()
        if folders:
            return True
        return False

    def file_name(self):
        return self.view.file_name()

    def top_folder(self):
        folders = self.view.window().folders()
        path = os.path.dirname(self.file_name())
        oldpath = ''
        while not path in folders and path != oldpath:
            oldpath = path
            path = os.path.dirname(path)
        if path == oldpath:
            # problem - we didn't find ourselves in the list of open folders
            # fallback to using heuristics instead
            path = os.path.dirname(self.file_name())
            while not FindFiles.reachedTopLevelFolders(oldpath, path):
                oldpath = path
                path = os.path.dirname(path)
        Msgs.debug_msg("Top folder for this project is: " + path)
        return path

    def find_tested_file(self):
        Msgs.debug_msg("Looking for tested file")
        fq_classname = self.determine_full_class_name()
        if fq_classname is None:
            return None
        if fq_classname[-4:] == 'Test':
            fq_classname = fq_classname[:-4]

        filename = fq_classname + '.php'

        Msgs.debug_msg("Looking for tested file: " + os.path.basename(filename))

        files_to_find = []
        files_to_find.append(filename)
        files_to_find.append(os.path.basename(filename))

        filename = self.view.file_name()
        if filename[-8:] == 'Test.php':
            filename = filename[:-8] + '.php'

        path_to_search = os.path.dirname(self.file_name())
        path = FindFiles.find(self.top_folder(), path_to_search, files_to_find)
        if path is None:
            return None

        return [path, fq_classname]

    def find_test_file(self):
        Msgs.debug_msg("Looking for test file")
        classname = self.determine_full_class_name()
        Msgs.debug_msg("classname is: " + classname)
        if classname is None:
            return None

        classname = classname + 'Test'
        filename = classname + '.php'

        files_to_find = []
        files_to_find.append(filename)
        files_to_find.append(os.path.basename(filename))
        files_to_find.append(os.path.basename(self.view.file_name())[:-4] + 'Test.php')

        Msgs.debug_msg("Looking for test files: " + ', '.join(files_to_find))

        path_to_search = os.path.dirname(self.file_name())
        path = FindFiles.find(self.top_folder(), path_to_search, files_to_find)
        if path is None:
            return None

        return [path, classname]

    def determine_full_class_name(self):
        namespace = self.extract_namespace()
        classname = self.extract_classname()
        if classname is None:
            return None
        path = ''
        if len(namespace) > 0:
            namespace = namespace.replace('\\', '/')
            path = path + namespace + '/'
        classname = classname.replace('_', '/')
        path = path + classname
        return path

    def extract_namespace(self):
        namespaces = self.view.find_all("namespace ([A-Za-z0-9_\\\]+);")
        if namespaces is None or len(namespaces) == 0:
            return ''
        for namespace in namespaces:
            line = self.view.substr(namespace)
            return line[10:-1]

    def extract_classname(self):
        # Look for any classes in the current window
        class_regions = self.view.find_by_selector('entity.name.type.class')
        for r in class_regions:
            # return the first class we find
            return self.view.substr(r)
        # If we get here, then there are no classes in the current window
        return None


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
    last_checked_enabled = None

    def run(self, args):
        print 'Not implemented'

    def toggle_active_group(self):
        # where will we open it?
        num_groups = self.view.window().num_groups()
        if num_groups > 1:
            active_group = self.view.window().active_group()
            active_group = (active_group + 1) % 2
            if active_group >= num_groups:
                active_group = num_groups - 1
            Msgs.debug_msg("switching to group " + str(active_group))
            self.view.window().focus_group(active_group)

    def enabled_checked(self):
        self.last_checked_enabled = datetime.datetime.now()

    def needs_enabling(self):
        if self.last_checked_enabled is None or ProjectFiles.expired(self.last_checked_enabled):
            return True
        return False


class PhpunitRunTestsCommand(PhpunitTextBase):
    path_to_config = None
    file_to_test = None

    def run(self, args):
        Msgs.operation = "PhpunitRunTestsClassCommand.run"

        cmd = PhpunitCommand(self.view.window())
        cmd.run(self.path_to_config, self.file_to_test)

    def description(self):
        Msgs.operation = "PhpunitRunTestsClassCommand.description"
        if self.file_to_test is None:
            return self.cannot_find_test_file()
        if self.path_to_config is None:
            return self.cannot_find_xml()
        return 'Run Tests ...'

    def is_enabled(self):
        Msgs.operation = "PhpunitRunTestsClassCommand.is_enabled"
        Msgs.debug_msg('called')
        self.enabled_checked()

        self.file_to_test = None
        self.path_to_config = None

        if not self.has_project_open():
            return False
        if not self.is_php_buffer():
            return False

        if self.is_test_buffer() or self.is_tests_buffer():
            test_file_to_open = [self.view.file_name()]
            tested_file_to_open = self.find_tested_file()
        else:
            test_file_to_open = self.find_test_file()
            tested_file_to_open = [self.view.file_name()]

        if test_file_to_open is None or tested_file_to_open is None:
            return False

        self.file_to_test = test_file_to_open[0]
        self.path_to_config = self.findPhpunitXml(self.file_to_test)
        if self.path_to_config is None:
            return False
        return True

    def is_visible(self):
        if self.needs_enabling():
            self.is_enabled()

        Msgs.operation = "PhpunitRunTestsClassCommand.is_visible"
        Msgs.debug_msg('called')

        if self.is_php_buffer() and os.path.exists(self.view.file_name()):
            return True
        return False


class PhpunitOpenTestClassCommand(PhpunitTextBase):
    file_to_open = None

    def run(self, args):
        Msgs.operation = "PhpunitOpenTestClassCommand.run"

        # where will we open the file?
        self.toggle_active_group()

        # open the file
        self.view.window().open_file(self.file_to_open)

    def description(self):
        return 'Open Test Class'

    def is_enabled(self):
        Msgs.operation = "PhpunitOpenTestClassCommand.is_enabled"
        Msgs.debug_msg('called')
        self.enabled_checked()

        self.file_to_open = None

        if not self.has_project_open():
            return False
        if not self.is_php_buffer():
            return False
        if self.is_test_buffer() or self.is_tests_buffer():
            return False
        path = self.find_test_file()
        if path is None:
            return False
        self.file_to_open = path[0]
        return True

    def is_visible(self):
        if self.needs_enabling():
            self.is_enabled()

        Msgs.operation = "PhpunitOpenTestClassCommand.is_visible"
        Msgs.debug_msg('called')

        if self.file_to_open is not None:
            return True
        return False


class PhpunitOpenClassBeingTestedCommand(PhpunitTextBase):
    file_to_open = None

    def run(self, args):
        Msgs.operation = "PhpunitOpenClassBeingTestedCommand.run"

        # where will we open the file?
        self.toggle_active_group()

        # open the file
        self.view.window().open_file(self.file_to_open)

    def description(self):
        return 'Open Class Being Tested'

    def is_enabled(self):
        Msgs.operation = "PhpunitOpenClassBeingTestedCommand.is_enabled"
        Msgs.debug_msg('called')
        self.enabled_checked()

        self.file_to_open = None

        if not self.has_project_open():
            return False
        if not self.is_php_buffer():
            return False
        if not self.is_test_buffer():
            return False
        if self.is_tests_buffer():
            return False
        path = self.find_tested_file()
        if path is None:
            return False
        self.file_to_open = path[0]
        return True

    def is_visible(self):
        if self.needs_enabling():
            self.is_enabled()

        Msgs.operation = "PhpunitOpenClassBeingTestedCommand.is_visible"
        Msgs.debug_msg('called')

        if self.file_to_open is not None:
            return True
        return False


class PhpunitToggleClassTestClassCommand(PhpunitTextBase):
    file_to_open = None

    def run(self, args):
        Msgs.operation = "PhpunitToggleClassTestClassCommand.run"

        # where will we open the file?
        self.toggle_active_group()

        # open the file
        self.view.window().open_file(self.file_to_open)

    def is_enabled(self):
        Msgs.operation = "PhpunitToggleClassTestClassCommand.is_enabled"
        Msgs.debug_msg('called')
        self.enabled_checked()

        self.file_to_open = None

        if not self.has_project_open():
            return False
        if not self.is_php_buffer():
            return False
        if self.is_test_buffer() or self.is_tests_buffer():
            file_to_open = self.find_tested_file()
        else:
            file_to_open = self.find_test_file()

        if file_to_open is None:
            return False

        self.file_to_open = file_to_open[0]
        return True

    def is_visible(self):
        if self.needs_enabling():
            self.is_enabled()

        Msgs.operation = "PhpunitToggleClassTestClassCommand.is_visible"
        Msgs.debug_msg('called')

        if self.file_to_open is not None:
            return True
        return False

    def description(self):
        return 'Toggle Between Code And Test File'


class PhpunitOpenPhpunitXmlCommand(PhpunitTextBase):
    file_to_open = None

    def run(self, args):
        Msgs.operation = "PhpunitOpenPhpunitXmlCommand.run"

        # where will we open the file?
        self.toggle_active_group()

        # open the file
        self.view.window().open_file(self.file_to_open)

    def description(self):
        return 'Open phpunit.xml'

    def is_visible(self):
        if self.needs_enabling():
            self.is_enabled()

        Msgs.operation = "PhpunitOpenPhpunitXmlCommand.is_visible"
        Msgs.debug_msg('called')

        if self.file_to_open is not None:
            return True
        return False

    def is_enabled(self):
        Msgs.operation = "PhpunitOpenPhpunitXmlCommand.is_enabled"
        Msgs.debug_msg('called')
        self.enabled_checked()

        self.file_to_open = None

        if not self.has_project_open():
            return False
        if not self.is_php_buffer():
            return False
        if self.is_phpunitxml():
            return False
        if self.is_test_buffer() or self.is_tests_buffer():
            filename = self.view.file_name()
        else:
            filename = self.find_test_file()
            if filename is not None:
                filename = filename[0]
            else:
                filename = self.view.file_name()
        path = self.findPhpunitXml(filename)
        if path is None:
            return False
        self.file_to_open = path
        return True


class PhpunitRunThisPhpunitXmlCommand(PhpunitTextBase):
    def run(self, args):
        Msgs.operation = "PhpunitRunThisPhpunitXmlCommand.run"
        phpunit_xml_file = self.file_name()
        cmd = PhpunitCommand(self.view.window())
        cmd.run(phpunit_xml_file)

    def is_enabled(self):
        Msgs.operation = "PhpunitRunThisPhpunitXmlCommand.is_enabled"
        Msgs.debug_msg('called')
        self.enabled_checked()

        if not self.has_project_open():
            return False
        return self.is_phpunitxml()

    def is_visible(self):
        if self.needs_enabling():
            self.is_enabled()

        Msgs.operation = "PhpunitRunThisPhpunitXmlCommand.is_visible"
        Msgs.debug_msg('called')

        if not self.has_project_open():
            return False
        return self.is_phpunitxml()

    def description(self, paths=[]):
        return 'Run Using This XML File...'


class PhpunitRunAllTestsCommand(PhpunitTextBase):
    path_to_config = None

    def run(self, args):
        Msgs.operation = "PhpunitRunAllTestsCommand.run"
        cmd = PhpunitCommand(self.view.window())
        cmd.run(self.path_to_config)

    def description(self):
        return 'Run All Unit Tests...'

    def is_enabled(self):
        Msgs.operation = "PhpunitRunAllTestsCommand.is_enabled"
        Msgs.debug_msg('called')
        self.enabled_checked()

        self.path_to_config = None
        if not self.has_project_open():
            return False
        if not self.is_php_buffer():
            return False
        if self.is_phpunitxml():
            return False
        if self.is_test_buffer() or self.is_tests_buffer():
            filename = self.view.file_name()
        else:
            filename = self.find_test_file()
            if filename is not None:
                filename = filename[0]
            else:
                filename = self.view.file_name()
        path = self.findPhpunitXml(filename)
        if path is None:
            return False

        self.path_to_config = path
        return True

    def is_visible(self):
        if self.needs_enabling():
            self.is_enabled()

        Msgs.operation = "PhpunitRunAllTestsCommand.is_visible"
        Msgs.debug_msg('called')

        if self.path_to_config is not None:
            return True
        return False


class PhpunitNotAvailableCommand(PhpunitTextBase):
    def is_visible(self):
        Msgs.operation = "PhpunitNotAvailableCommand.is_visible"
        Msgs.debug_msg('called')

        if not self.has_project_open():
            return True
        if self.is_php_buffer():
            return False
        if self.is_phpunitxml():
            return False
        return True

    def is_enabled(self):
        Msgs.operation = "PhpunitNotAvailableCommand.is_enabled"
        Msgs.debug_msg('called')

        return False

    def description(self):
        Msgs.operation = "PhpunitNotAvailableCommand.description"
        Msgs.debug_msg('called')

        if not self.has_project_open():
            return self.not_in_project()
        if not self.is_php_buffer():
            return self.not_php_file(self.view.settings().get('syntax'))
        return self.cannot_find_xml()


class PhpunitFlushCacheCommand(PhpunitTextBase):
    def is_enabled(self):
        Msgs.operation = "PhpunitFlushCacheCommand.is_enabled"
        Msgs.debug_msg('called')

        Prefs.load()
        FoundFiles.removeCache()
        ProjectFiles.buildFilesList(self.top_folder())

        # special case!!
        #
        # we call enabled_checked() AT THE END because it must have a
        # timestamp no earlier than the time we rebuilt the ProjectFiles
        # cache
        self.enabled_checked()

        return False

    def is_visible(self):
        if self.needs_enabling():
            self.is_enabled()

        Msgs.operation = "PhpunitFlushCacheCommand.is_visible"
        Msgs.debug_msg('called')

        return False


class PhpunitWindowBase(sublime_plugin.WindowCommand, ActiveWindow):
    def run(self, paths=[]):
        print "not implemented"


class RunPhpunitOnXmlCommand(PhpunitWindowBase):
    def run(self, paths=[]):
        Msgs.operation = "RunPhpunitOnXmlCommand.run"
        Msgs.debug_msg('called')

        self.determine_filename(paths)
        filename = self.file_name()
        cmd = PhpunitCommand(self.window)
        cmd.run(filename)

    def is_enabled(self, paths=[]):
        Msgs.operation = "RunPhpunitOnXmlCommand.is_enabled"
        Msgs.debug_msg('called')

        return self.is_visible(paths)

    def is_visible(self, paths=[]):
        Msgs.operation = "RunPhpunitOnXmlCommand.is_visible"
        Msgs.debug_msg('called')

        self.determine_filename(paths)
        return self.is_phpunitxml()

    def description(self, paths=[]):
        return 'Run PHPUnit Using This XML File...'
