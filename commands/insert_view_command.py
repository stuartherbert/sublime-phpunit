import sublime
import sublime_plugin

class InsertViewCommand(sublime_plugin.TextCommand):
	def run(self, edit, string=''):
		self.view.insert(edit, self.view.size(), string)