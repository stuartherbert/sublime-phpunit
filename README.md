Sublime PHP
===========

This is a collection of (hopefully) useful extras for writing PHP code using the excellent Sublime Text 2 editor.

Installation
------------

We're waiting to be added to [Package Control](http://wbond.net/sublime_packages/package_control), so for now you'll need to clone this repo into your Sublime Text 2 "Packages/" folder.

PHPUnit Support For Sublime Text 2
----------------------------------

This plugin adds support for running PHPUnit tests from inside Sublime Text 2.

Right-click in the editor to:

* Run all unit tests (available in all PHP files)
* Run the unit tests in the current file (only available in *Test.php files)
* Run PHPUnit, using the current XML config file (available inside the XML config file)

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

We add the following snippets to speed up writing PHP code.

To use any of the snippets, simply type the name of the snippet, then press the <TAB> key.  Sublime Text 2 will insert the snippet, and you can then use the <TAB> key to move through any placeholders that you need to replace.

* __license-newbsd__: insert the new BSD license (eg into LICENSE.md-type files)
* __php-getset__: create getter/setter methods quickly and easily (based on a snippet originally published by @akrabat)
* __php-newbsd__: insert the new BSD license as a PHP docblock
* __php-section-comment__: insert a prominent comment to help break up the sections of your class
* __phpunit-test__: create a new test method inside your TestCase class
* __phpunit-testcase__: create a new TestCase class to put your tests inside

Contributions Welcome
---------------------

Requests for features, and pull requests with patches, are most welcome :)
