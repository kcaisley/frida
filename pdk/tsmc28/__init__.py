"""TSMC28 HDL21-style PDK package for FRIDA."""

from typing import Optional

from hdl21.pdk import register

from . import pdk_logic
from .pdk_logic import *

install: Optional[Install] = None

register(pdk_logic)
