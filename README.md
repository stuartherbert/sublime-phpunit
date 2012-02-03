Sublime PHP
===========

This is a collection of (hopefully) useful extras for writing PHP code using the excellent Sublime Text 2 editor.

PHPUnit Support For Sublime Text 2
----------------------------------

This plugin adds support for running PHPUnit tests from inside Sublime Text 2.

We add right-click menu options to:

* Run all unit tests (available in all PHP files)
* Run the unit tests in the current file (only available in *Test.php files)

To make this work, you need to create a phpunit.xml.dist or phpunit.xml file in the top-level folder of your code (projects using [Phix](http://phix-project.org) get this for free).

You can also right-click on any phpunit.xml or phpunit.xml.dist file in your sidebar to use it to run PHPUnit.

_PHPUnit support is based on the [Ruby Tests plugin](https://github.com/maltize/sublime-text-2-ruby-tests)_

Snippets
--------

We add the following snippets to speed up writing PHP code.

To use any of the snippets, simply type the name of the snippet, then press the <TAB> key.  Sublime Text 2 will insert the snippet, and you can then use the <TAB> key to move through any placeholders that you need to replace.

* __license-newbsd__: insert the new BSD license (eg into LICENSE.md-type files)
* __php-getset__: create getter/setter methods quickly and easily (based on a snippet originally published by @akrabat)
* __php-newbsd__: insert the new BSD license as a PHP docblock
* __php-section-comment__: insert a prominent comment to help break up the sections of your class

Contributions Welcome
---------------------

Requests for features, and pull requests with patches, are most welcome :)