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

class TestClass:
    def __init__(self, value):
        self.value = value

objTestClass = TestClass(10)

print(objTestClass)
print(TestClass)

# print("class based approach")
# print(MyModule)
# print(MyModule.i)
# print(MyModule.o)
# print(MyModule.s)

print("done!")