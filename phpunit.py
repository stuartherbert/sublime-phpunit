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

Prefs.load()


def debug_msg(msg):
    if Prefs.debug == 1:
        print "[PHPUnit Plugin] " + msg


# the AsyncProcess class has been cribbed from:
# https://github.com/maltize/sublime-text-2-ruby-tests/blob/master/run_ruby_test.py


class AsyncProcess(object):
    def __init__(self, cmd, cwd, listener):
        self.listener = listener
        debug_msg("DEBUG_EXEC: " + ' '.join(cmd))
        if os.name == 'nt':
            # we have to run PHPUnit via the shell to get it to work for everyone on Windows
            # no idea why :(
            # I'm sure this will prove to be a terrible idea
            self.proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
        else:
            # Popen works properly on OSX and Linux
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
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
                self.listener.append_data(self.proc, "\n--- PROCESS COMPLETE ---")
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
    def run(self, path, testfile='', classname=''):
        self.show_empty_output()

        if Prefs.path_to_phpunit is not False:
            args = [Prefs.path_to_phpunit]
        else:
            args = ["phpunit"]

        # Add the additional arguments from the settings file to the command
        for key, value in Prefs.phpunit_additional_args.items():
            arg = key
            if value != "":
                arg += "=" + value
            args.append(arg)

        if len(path) > 0:
            args.append("-c")
            args.append(path[1])
        if classname != '':
            args.append(classname)
        if testfile != '':
            args.append(testfile)

        self.append_data(self, "# Running in folder: " + path[0] + "\n")
        self.append_data(self, "$ " + ' '.join(args) + "\n")
        self.start_async("Running PHPUnit", args, path[0])


class AvailableFiles:
    searched_folders = {}
    search_results_cache = {}
    last_search_time = None

    @staticmethod
    def expireSearchResultsCache(forced=False):
        debug_msg("resetting list of searched folders")
        AvailableFiles.searched_folders = {}

        now = datetime.datetime.now()
        if AvailableFiles.last_search_time is not None:
            since = AvailableFiles.last_search_time + datetime.timedelta(seconds=60)
        if AvailableFiles.last_search_time is None or now > since or forced is True:
            debug_msg("emptying search results cache")
            AvailableFiles.last_search_time = now
            AvailableFiles.search_results_cache = {}

    @staticmethod
    def forgetLastSearchFor(cached_files):
        for cached_file in cached_files:
            if cached_file in AvailableFiles.search_results_cache:
                del AvailableFiles.search_results_cache[cached_file]

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
    def searchStraightUpwardsFor(top_folder, path, suffixes):
        AvailableFiles.expireSearchResultsCache()
        debug_msg("---- New search straight upwards ----")

        # do we know where these files are?
        for suffix in suffixes:
            if suffix in AvailableFiles.search_results_cache:
                debug_msg("Found " + suffix + " in cached search results")
                if AvailableFiles.search_results_cache[suffix] is None:
                    return None
                return [suffix, AvailableFiles.search_results_cache[suffix]]

        result = AvailableFiles._searchStraightUpwardsFor(top_folder, '', path, suffixes)
        if result is None:
            for suffix in suffixes:
                AvailableFiles.search_results_cache[suffix] = None
            return None
        else:
            AvailableFiles.search_results_cache[result[0]] = result[1]
        # print result
        return result

    @staticmethod
    def _searchStraightUpwardsFor(top_folder, oldpath, path, suffixes):
        debug_msg("Looking in " + path)
        for suffix in suffixes:
            filenameToTest = os.path.join(path, suffix)
            debug_msg("Looking for " + filenameToTest)
            if os.path.exists(filenameToTest):
                return [suffix, filenameToTest]

        if AvailableFiles.reachedTopLevelFolder(top_folder, oldpath, path):
            return None

        return AvailableFiles._searchStraightUpwardsFor(top_folder, path, os.path.dirname(path), suffixes)

    @staticmethod
    def searchUpwardsFor(top_folder, path, suffixes):
        AvailableFiles.expireSearchResultsCache()
        debug_msg("---- New search upwards ----")

        # do we know where these files are?
        for suffix in suffixes:
            if suffix in AvailableFiles.search_results_cache:
                debug_msg("Found " + suffix + " in cached search results")
                if AvailableFiles.search_results_cache[suffix] is None:
                    return None
                return [suffix, AvailableFiles.search_results_cache[suffix]]

        result = AvailableFiles._searchUpwardsFor(top_folder, '', path, suffixes)
        if result is None:
            for suffix in suffixes:
                AvailableFiles.search_results_cache[suffix] = None
            return None
        else:
            AvailableFiles.search_results_cache[result[0]] = result[1]
        return result

    @staticmethod
    def _searchUpwardsFor(top_folder, oldpath, path, suffixes):
        for suffix in suffixes:
            filenameToTest = os.path.join(path, suffix)
            debug_msg("Looking for " + filenameToTest)
            if os.path.exists(filenameToTest):
                return [suffix, filenameToTest]

        found_path = AvailableFiles._searchDownwardsFor(path, suffixes)
        if found_path is not None:
            return found_path

        if AvailableFiles.reachedTopLevelFolder(top_folder, oldpath, path):
            return None

        return AvailableFiles._searchUpwardsFor(top_folder, path, os.path.dirname(path), suffixes)

    @staticmethod
    def searchDownwardsFor(path, suffixes):
        AvailableFiles.expireSearchResultsCache()
        debug_msg("---- New search downwards ----")

        # do we know where these files are?
        for suffix in suffixes:
            if suffix in AvailableFiles.search_results_cache:
                debug_msg("Found " + suffix + " in cached search results")
                if AvailableFiles.search_results_cache[suffix] is None:
                    return None
                return [suffix, AvailableFiles.search_results_cache[suffix]]

        result = AvailableFiles._searchDownwardsFor(path, suffixes)
        if result is None:
            for suffix in suffixes:
                AvailableFiles.search_results_cache[suffix] = None
            return None
        else:
            AvailableFiles.search_results_cache[result[0]] = result[1]
            # print result
            return result

    @staticmethod
    def _searchDownwardsFor(path, suffixes):
        # does the path exist?
        if not os.path.exists(path):
            return None

        # does the file exist at this level?
        for suffix in suffixes:
            filenameToTest = os.path.join(path, suffix)
            if os.path.exists(filenameToTest):
                return [suffix, filenameToTest]

        # no it does not
        #
        # we're going to have to walk what might be an unsearchably-large
        # folder structure
        #
        # there have been problems with this search taking too long, so now
        # we cap this search time
        start = datetime.datetime.now()

        # no, so look in our subfolders
        for root, dirs, names in os.walk(path):
            # avoid hidden places
            if '.' in root:
                continue
            # strip out all hidden folders
            dirs[:] = [d for d in dirs if d[0] != '.']
            # strip out all the folders we want to exclude
            dirs[:] = [d for d in dirs if d not in Prefs.folder_exclusions]
            # look inside what is left
            for subdir in dirs:
                # print "looking at dir " + path + ' ' + subdir
                pathToSearch = os.path.join(root, subdir)
                # print "looking at  - " + root + ' ' + subdir
                if pathToSearch in AvailableFiles.searched_folders:
                    # print "Already searched " + pathToSearch + "; skipping"
                    continue
                AvailableFiles.searched_folders[pathToSearch] = True
                # if we get here, we have not discarded this folder yet
                for suffix in suffixes:
                    filenameToTest = os.path.join(pathToSearch, suffix)
                    # print "Looking in subfolders for " + filenameToTest
                    if os.path.exists(filenameToTest):
                        # print "Found " + filenameToTest
                        return [suffix, filenameToTest]
                # make sure we're not taking too long
                since = datetime.datetime.now()
                if since - start > datetime.timedelta(seconds=Prefs.max_search_secs):
                    sublime.status_message("Timeout whilst searching for phpunit.xml")
                    return None

        return None

    @staticmethod
    def searchNamedPlacesFor(top_folder, places, suffixes):
        for place in places:
            pathToTest = os.path.join(top_folder, place)
            for suffix in suffixes:
                filenameToTest = os.path.join(pathToTest, suffix)
                if os.path.exists(filenameToTest):
                    return [suffix, filenameToTest]
        return None


class ActiveFile:
    def is_test_buffer(self):
        filename = self.file_name()
        if not os.path.isfile(filename):
            debug_msg("Buffer is not a test file; is not a real file")
            return False
        filename = os.path.splitext(filename)[0]
        if filename.endswith('Test'):
            debug_msg("Buffer is a test file")
            return True
        debug_msg("Buffer is not a test file")
        return False

    def is_tests_buffer(self):
        filename = self.file_name()
        if not os.path.isfile(filename):
            debug_msg("Buffer is not a testsuite file; is not a real file")
            return False
        filename = os.path.splitext(filename)[0]
        if filename.endswith('Tests'):
            debug_msg("Buffer is a testsuite file")
            return True
        debug_msg("Buffer is not a testsuite file")
        return False

    def is_phpunitxml(self):
        # is this a phpunit.xml file?
        filename = self.file_name()
        if not os.path.isfile(filename):
            debug_msg("Buffer is not phpunit.xml; is not a real file")
            return False
        filename = os.path.basename(filename)
        if filename == 'phpunit.xml' or filename == 'phpunit.xml.dist':
            debug_msg("Buffer is a phpunit.xml file")
            return True
        debug_msg("Buffer is not a phpunit.xml file")
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

    def findPhpunitXml(self, search_from, folders={}):
        debug_msg("Looking for phpunit.xml of some kind")
        dir_name = search_from
        if not os.path.isdir(dir_name):
            dir_name = os.path.dirname(dir_name)

        files_to_find = ['phpunit.xml', 'phpunit.xml.dist']
        debug_msg("Looking for " + ', '.join(files_to_find))

        # check in the places given in hints
        result = AvailableFiles.searchNamedPlacesFor(self.top_folder(), Prefs.phpunit_xml_location_hints, files_to_find)
        if result is not None:
            return [os.path.dirname(result[1]), os.path.basename(result[1])]

        # empty the cached results so that we can try again
        AvailableFiles.forgetLastSearchFor(files_to_find)

        # straight-line search - fastest for most people
        result = AvailableFiles.searchStraightUpwardsFor(self.top_folder(), dir_name, files_to_find)
        if result is not None:
            return [os.path.dirname(result[1]), os.path.basename(result[1])]

        # empty the cached results so that we can try again
        AvailableFiles.forgetLastSearchFor(files_to_find)

        # okay, so where is it?
        result = AvailableFiles.searchDownwardsFor(self.top_folder(), files_to_find)
        if result is not None:
            return [os.path.dirname(result[1]), os.path.basename(result[1])]
        return None

    def error_message(self, message):
        sublime.status_message(message)

    def cannot_find_xml(self):
        return "Cannot find phpunit.xml or phpunit.xml.dist file"

    def cannot_find_test_file(self):
        return "Cannot find file containing unit tests"

    def cannot_find_tested_file(self):
        return "Cannot find file to be tested"

    def not_php_file(self, syntax):
        debug_msg(syntax)
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
            debug_msg("Buffer is a PHP buffer")
            return True
        # is this a PHP buffer?
        if re.search('.+\PHP.tmLanguage', self.view.settings().get('syntax')):
            return True
        # if we get here, we're not sure what else to try
        debug_msg("Buffer is not a PHP buffer; extension is: " + ext + "; syntax is: " + self.view.settings().get('syntax'))
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
            while not AvailableFiles.reachedTopLevelFolders(oldpath, path):
                oldpath = path
                path = os.path.dirname(path)
        debug_msg("Top folder for this project is: " + path)
        return path

    def find_tested_file(self):
        debug_msg("Looking for tested file")
        fq_classname = self.determine_full_class_name()
        if fq_classname is None:
            return None
        if fq_classname[-4:] == 'Test':
            fq_classname = fq_classname[:-4]

        filename = fq_classname + '.php'

        debug_msg("Looking for tested file: " + os.path.basename(filename))

        files_to_find = []
        files_to_find.append(filename)
        files_to_find.append(os.path.basename(filename))

        path_to_search = os.path.dirname(self.file_name())
        path = AvailableFiles.searchUpwardsFor(self.top_folder(), path_to_search, files_to_find)
        if path is None:
            return None

        return [path[1], fq_classname]

    def find_test_file(self):
        debug_msg("Looking for test file")
        classname = self.determine_full_class_name()
        if classname is None:
            return None

        classname = classname + 'Test'
        filename = classname + '.php'

        files_to_find = []
        files_to_find.append(filename)
        files_to_find.append(os.path.basename(filename))

        debug_msg("Looking for test files: " + ', '.join(files_to_find))

        path_to_search = os.path.dirname(self.file_name())
        path = AvailableFiles.searchUpwardsFor(self.top_folder(), path_to_search, files_to_find)
        if path is None:
            return None

        return [path[1], classname]

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
        classes = self.view.find_all("class [A-Za-z0-9_]+")
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

    def toggle_active_group(self):
        # where will we open it?
        num_groups = self.view.window().num_groups()
        if num_groups > 1:
            active_group = self.view.window().active_group()
            active_group = (active_group + 1) % 2
            if active_group >= num_groups:
                active_group = num_groups - 1
            debug_msg("switching to group " + str(active_group))
            self.view.window().focus_group(active_group)


class PhpunitTestThisClass(PhpunitTextBase):
    def run(self, args):
        file_to_test = self.find_test_file()
        if file_to_test is None:
            self.error_message(self.cannot_find_test_file())
            return

        path = self.findPhpunitXml(file_to_test[0], self.view.window().folders())
        if path is None:
            self.error_message(self.cannot_find_xml())
            return

        cmd = PhpunitCommand(self.view.window())
        cmd.run(path, file_to_test[0], file_to_test[1])

    def description(self):
        if self.is_test_buffer() or self.is_tests_buffer():
            return None
        test_file = self.find_test_file()
        if test_file is None:
            return self.cannot_find_test_file()
        path = self.findPhpunitXml(test_file[0], self.view.window().folders())
        if path is None:
            return self.cannot_find_xml()
        return 'Test This Class...'

    def is_enabled(self):
        if not self.is_php_buffer():
            return False
        if self.is_test_buffer() or self.is_tests_buffer():
            return False
        test_file = self.find_test_file()
        if test_file is None:
            return False
        path = self.findPhpunitXml(test_file[0], self.view.window().folders())
        if path is None:
            return False
        return True

    def is_visible(self):
        if not self.is_php_buffer():
            return False
        if self.is_test_buffer() or self.is_tests_buffer():
            return False
        test_file = self.find_test_file()
        if test_file is None:
            return False
        return True


class PhpunitOpenTestClass(PhpunitTextBase):
    def run(self, args):
        file_to_open = self.find_test_file()
        if file_to_open is None:
            self.error_message(self.cannot_find_test_file())
            return

        # where will we open the file?
        self.toggle_active_group()

        # open the file
        self.view.window().open_file(file_to_open[0])

    def description(self):
        if self.is_enabled():
            return 'Open Test Class'
        return self.cannot_find_test_file()

    def is_enabled(self):
        if not self.is_php_buffer():
            return False
        if self.is_test_buffer() or self.is_tests_buffer():
            return False
        path = self.find_test_file()
        if path is None:
            return False
        return True

    def is_visible(self):
        if not self.is_php_buffer():
            return False
        if self.is_test_buffer() or self.is_tests_buffer():
            return False
        return True


class PhpunitOpenClassBeingTested(PhpunitTextBase):
    def run(self, args):
        file_to_open = self.find_tested_file()
        if file_to_open is None:
            self.error_message(self.cannot_find_tested_file())
            return

        # where will we open the file?
        self.toggle_active_group()

        # open the file
        self.view.window().open_file(file_to_open[0])

    def description(self):
        file_to_open = self.find_tested_file()
        if file_to_open is None:
            return self.cannot_find_tested_file()
        return 'Open Class Being Tested'

    def is_enabled(self):
        if not self.is_php_buffer():
            return False
        if not self.is_test_buffer():
            return False
        if self.is_tests_buffer():
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
        if self.is_tests_buffer():
            return False
        return True


class PhpunitOpenPhpunitXml(PhpunitTextBase):
    def run(self, args):
        if self.is_test_buffer() or self.is_tests_buffer():
            filename = self.view.file_name()
        else:
            filename = self.find_test_file()
            if filename is not None:
                filename = filename[0]
        path = self.findPhpunitXml(filename, self.view.window().folders())
        if path is None:
            self.cannot_find_xml()
            return

        # where will we open the file?
        self.toggle_active_group()

        # open the file
        self.view.window().open_file(os.path.join(path[0], path[1]))

    def description(self):
        return 'Open phpunit.xml'

    def is_enabled(self):
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
        if filename is None:
            return False
        path = self.findPhpunitXml(filename, self.view.window().folders())
        if path is None:
            return False
        return True

    def is_visible(self):
        return self.is_enabled()


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
        path = self.findPhpunitXml(self.view.file_name(), self.view.window().folders())
        if path is None:
            self.error_message(self.cannot_find_xml())
            return

        file_to_test = self.determineTestFile()
        cmd = PhpunitCommand(self.view.window())
        cmd.run(path, file_to_test)

    def description(self):
        path = self.findPhpunitXml(self.view.file_name(), self.view.window().folders())
        if path is None:
            return self.cannot_find_xml()
        return 'Run These Tests...'

    def is_enabled(self):
        if not self.is_php_buffer():
            return False
        if not self.is_test_buffer() and not self.is_tests_buffer():
            return False
        path = self.findPhpunitXml(self.view.file_name(), self.view.window().folders())
        if path is None:
            return False
        return True

    def is_visible(self):
        if not self.is_php_buffer():
            return False
        if not self.is_test_buffer() and not self.is_tests_buffer():
            return False
        return True


class PhpunitRunAllTestsCommand(PhpunitTextBase):
    def run(self, args):
        if self.is_test_buffer() or self.is_tests_buffer():
            filename = self.view.file_name()
        else:
            filename = self.find_test_file()
            if filename is not None:
                filename = filename[0]
        path = self.findPhpunitXml(filename, self.view.window().folders())
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
        if self.is_test_buffer() or self.is_tests_buffer():
            filename = self.view.file_name()
        else:
            filename = self.find_test_file()
            if filename is not None:
                filename = filename[0]
        if filename is None:
            return False
        path = self.findPhpunitXml(filename, self.view.window().folders())
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
        if not self.is_php_buffer():
            return self.not_php_file(self.view.settings().get('syntax'))
        return self.cannot_find_xml()


class PhpunitFlushCacheCommand(PhpunitTextBase):
    def is_visible(self):
        Prefs.load()
        AvailableFiles.expireSearchResultsCache(forced=True)
        return False


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
        return 'Run PHPUnit Using This XML File...'
