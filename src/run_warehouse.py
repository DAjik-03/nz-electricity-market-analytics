"""Phase 2 PostgreSQL entry point. Source files are already pinned locally."""
import argparse
from warehouse.loader import run

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['init','load','validate'])
    command=parser.parse_args().command
    if command=='validate':
        from warehouse.validation import main
        main()
    else:
        run(command)
