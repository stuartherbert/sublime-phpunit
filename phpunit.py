import re
import sublime
import sublime_plugin

class PhpunitBase(sublime_plugin.TextCommand):
    def is_php_buffer(self):
        # is this a PHP buffer?
        if re.search('.+\PHP.tmLanguage', self.view.settings().get('syntax')):
            return True
        return False

    def window(self):
        return self.view.window()

    def show_output(self):
        self.ensure_output_panel()
        self.window().run_command("show_panel", {"panel": "output.phpunit"})

    def show_empty_output(self):
        self.ensure_output_panel()
        self.clear_test_view()
        self.show_output()

    def ensure_output_panel(self):
        if not hasattr(self, 'output_window'):
            self.output_window = self.window().get_output_panel("phpunit")

    def clear_test_view(self):
        self.output_window.set_read_only(False)
        edit = self.output_window.begin_edit()
        self.output_window.erase(edit, sublime.Region(0, self.output_window.size()))
        self.output_window.end_edit(edit)
        self.output_window.set_read_only(True)

class PhpunitTestThisClass(PhpunitBase):
    def run(self, args):
        self.show_output()

    def description(self):
        return 'Test This Class...'

    def is_enabled(self):
        return self.is_php_buffer()

    def is_visible(self):
        return self.is_php_buffer()

class PhpunitRunAllTestsCommand(PhpunitBase):
    def run(self, args):
        self.show_output()

    def description(self):
        return 'Run All Unit Tests...'

    def is_enabled(self):
        return self.is_php_buffer()

    def is_visible(self):
        return self.is_enabled()

class PhpunitShowOutputCommand(PhpunitBase):
    def run(self, args):
        self.show_output()

    def description(self):
        return 'Show Test Output...'

class PhpunitNotAvailableCommand(PhpunitBase):
    def is_visible(self):
        if not self.is_php_buffer():
            return True
        return False

    def is_enabled(self):
        return False

    def description(self):
        return 'PHPUnit tests can only be run on PHP windows'