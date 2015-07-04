Sublime PHPUnit
===============

This plugin adds PHPUnit support to Sublime Text 2 & 3.

Installation
------------

Use [Package Control](http://wbond.net/sublime_packages/package_control) (Preferences -> Package Control -> Install Package -> PHPUnit) to install this plugin.

PHPUnit Support For Sublime Text
--------------------------------

This plugin adds support for running PHPUnit tests from inside Sublime Text.

Right-click in the editor to:

* Run all unit tests
* Run the unit tests for the current file
* Run the unit tests in the current file
* Run PHPUnit, using the current XML config file
* Goto the file containing the tests or the file being tested

Right-click in the side-bar to:

* Run the unit tests in the current file
* Run all the unit tests
* Run PHPUnit, using the selected XML config file

You can also open up the Command Palette (CTRL + SHIFT + P on Linux), and type
'PHPUnit' to see what you can do with PHPUnit in the currently open file.

To make this work, you need to create a phpunit.xml.dist or phpunit.xml file for your code (projects using [Phix](http://phix-project.org) get this for free).  The Sublime-PHP plugin searches the folders upwards from whatever you are trying to test, using the first phpunit.xml or phpunit.xml.dist that it finds.  Make sure that your phpunit.xml file is either at the top of your tests folder (or even further up), and this plugin will work for you.

_PHPUnit support is based on the [Ruby Tests plugin](https://github.com/maltize/sublime-text-2-ruby-tests)_

Snippets
--------

We add the following snippets to speed up writing PHP test code.

To use any of the snippets, simply type the name of the snippet, then press the <TAB> key.  Sublime Text 2 will insert the snippet, and you can then use the <TAB> key to move through any placeholders that you need to replace.

* __phpunit-test__: create a new test method inside your TestCase class
* __phpunit-testcase__: create a new TestCase class to put your tests inside


Keyboard Shortcuts
------------------

It is also possible to run the unit tests just by hitting a key combo.
This is done by adding a new row to your own personal "Key bindings - User" which can be found in the preferences menu.

    { "keys": ["ctrl+tab"], "command": "phpunit_run_all_tests" }
  
Other available commands:

* phpunit\_flush\_cache
* phpunit\_run\_tests
* phpunit\_open\_test\_class
* phpunit\_open\_class\_being\_tested
* phpunit\_toggle\_class\_test\_class
* phpunit\_open\_phpunit\_xml
* phpunit\_run\_all\_tests
* phpunit\_run\_this\_phpunit\_xml

Contributions Welcome
---------------------

Requests for features, and pull requests with patches, are most welcome :)

Please make sure that your pull requests are against the 'develop' branch and not 'master'.
