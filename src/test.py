import hdl21 as h

@h.paramclass
class MyParams:
    # Required
    width = h.Param(dtype=int, desc="Width. Required")
    # Optional - including a default value
    text = h.Param(dtype=str, desc="Optional string", default="My Favorite Module")

@h.generator
def MyGen(params: MyParams) -> h.Module:
    # A very exciting first generator function
    m = h.Module()
    m.i = h.Input(width=params.w)
    return m

def MyFunct(x):
    return x + 2


p = MyParams(width=8, text="My Favorite Module")
#MyGen(p)

#MyParams(width=8, text="My Favorite Module")


print(p)