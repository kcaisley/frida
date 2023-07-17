# Notes
When creating a module from a class, some additional fancy stuff is happening... it's not just the same as creating an object from a standard class. For example. If we run this:

```python
class TestClass:
    def __init__(self, value):
        self.value = value

objTestClass = TestClass(10)

print(TestClass)
print(objTestClass)
```

We get:

```python
<class '__main__.TestClass'>
<__main__.TestClass object at 0x7f47b26698d0>
```

Notice how these signatures tell us that both the class and object are sort of 'runtime' objects.


For now examine these two runs:

```python
import hdl21 as h

m = h.Module(name="MyModule")
m.i = h.Input()
m.o = h.Output(width=8)
m.s = h.Signal()

print(m)

@h.module
class MyModule2:
    i = h.Input()
    o = h.Output(width=8)
    s = h.Signal()

print(MyModule2)
```

This yields:

```python
Module(name=MyModule)
Module(name=MyModule2)
```

Q: Why are these two annotated this way?

A: The print outputs for `Module(name=MyModule)` and `Module(name=MyModule2)` indicate that these are instances of a custom class (like `objTestClass`) named Module with specific attributes and values. The different annotations `Module(name=...)` are likely defined as part of the `__repr__` or `__str__` method within the Module class, which returns a string representation of the object.

# Steps

- Create basic VCO generator
- Work through Ravazi PLL book, comparing against real circuits
- Implement noise simulation via Spectre in HDL21
- Work on physical implementation in SKY130, 65nm, and 28nm
- Short feedback loops in sharing the work.

By the end of this week, I want to have a simulation of a VCO, in 130nm SKYWATER. I want to run it against Spectre, as I want to plot large signal noise, in an eye diagram. Contribute that code as a Pull request. Start from gated ring oscillator example provided by examples. 
