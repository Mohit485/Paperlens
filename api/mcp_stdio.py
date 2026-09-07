import builtins
import functools
import sys

builtins.print = functools.partial(print, file=sys.stderr)

from mcp_tools import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio", show_banner=False)