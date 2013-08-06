import sublime
import sublime_plugin

class EraseViewCommand(sublime_plugin.TextCommand):
	def run(self, edit, size=0):
		self.view.erase(edit, sublime.Region(0, size))