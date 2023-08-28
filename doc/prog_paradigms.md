specifying the type of a variable in a language doesn't necessarily mean that it is statically typed

the syntax advantage of dynamic languages are eroded once you work in a typeful language that has good type inference

picking types for the inputs and outputs of functions isn't seperate from the act of design

functional programming vs procedural/oo programming is a lot like static vs dynamic: constraints allow us to work faster, because they restrict our ability to think

python now supports 'type hints', but does this really provide the benefits of static typing?

Typing is defined as 'When types are check'

Therefore, Python is dynamically typed, as it is checked at run time
Whereas, C is statically typed, before run-time

Type checking has nothing to do with the language being compiled or interpreted

While python is interpreted and dynamically typed (types checked at runtime), it is **not** weakly typed. It's strongly typed, and so if your try and write

```
'3' + 5 
```

in Python, you're going to have a bad day.


unit test, integration test, end-to-end test, functional test

test driven development vs behavior driven development vs user-driven development

Adding extra contents to a simple code file, specifying the nature and types of inputs and outputs

Small problems occur not because tests are good, but because the areas with the problems aren't well defined and are fragile.

The way you do it right, is to do it wrong at first but fast enough that you do it enough to learn to do it right. 

Test driven development was introduced to prevent bad developers from committing bad code.

People over-optimise to make the first version of something last forever. Don't lie to yourself, thinking that you're not still on the first version is probably a lie.

The amount of controls and tests will depend on the penalty for mistakes.



tree sitter, language syntax trees, parsing

	* can be used for compilation, or for intelligent tools like syntax highlighting, code folding, and variable highlighting all instances under cursor

the Lanugage Server Protocol (LSP) is a standardized with for an IDE to communicate with an external language server, to provide features like auto complete, go to definition, or documentation on hover for a programming language

Pylance, Pyright (superceded), and Jedi are the main examples of python language servers

* Docstrings
* Signature help, with type information
* Parameter suggestions
* Code completion
* Auto-imports (as well as add and remove import code actions)
* As-you-type reporting of code errors and warnings (diagnostics)
* Code outline
* Code navigation
* Type checking mode
* Native multi-root workspace support
* IntelliCode compatibility
* Jupyter Notebooks compatibility
* Semantic highlighting





