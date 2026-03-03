import argparse
import importlib
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List
import logging

logger = logging.getLogger("rpkispool.cli")


@dataclass
class RPKIDate:
    year: str
    month: str
    day: str

    @classmethod
    def default(cls) -> "RPKIDate":
        """
        Return the default date (yesterday) as an RPKIDate instance.
        """
        return cls.parse((date.today() - timedelta(days=1)).strftime("%Y%m%d"))    

    @classmethod
    def parse(cls, value: str) -> "RPKIDate":
        m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", value)
        if not m:
            raise argparse.ArgumentTypeError(f"Invalid date format '{value}' (expected YYYYMMDD)")
        return cls(*m.groups())

    def __str__(self) -> str:
        return f"{self.year}{self.month}{self.day}"

# add new cli modules here
CLI_MODULES = [
    "rpkispool.cli.download",
]

def _load_modules() -> Dict[str, Any]:
    """
    Dynamically import CLI modules and return a mapping of command names to modules.
    """
    modules: Dict[str, Any] = {}

    for mod_name in CLI_MODULES:
        try:
            modules[mod_name.split(".")[-1]] = importlib.import_module(mod_name)
        except ImportError as e:
            print(f"Error importing module '{mod_name}': {e}", file=sys.stderr)
            sys.exit(1)

    return modules

def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="rpkispool-cli", description="RPKISpool CLI tool")
    parser.add_argument("--date", metavar="YYYYMMDD", type=RPKIDate.parse, default=RPKIDate.default(), help="Date to operate on (default: yesterday)")
    parser.add_argument("--output-dir", default="work/archives", metavar="DIR", type=Path, help="Output directory (default: work/archives)")
    parser.add_argument("--verbose", "-v", action="count", default=1, help="Increase verbosity")

    subparsers = parser.add_subparsers(dest="command")

    modules = _load_modules()

    for module in modules.values():
        module.add_parser(subparsers)

    args = parser.parse_args(argv)

    log_level = logging.WARNING
    if args.verbose >= 2:
        log_level = logging.DEBUG
    elif args.verbose == 1:
        log_level = logging.INFO

    logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)s: %(message)s")

    if args.command in modules:
        modules[args.command].run(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
