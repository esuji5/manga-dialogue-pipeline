#!/usr/bin/env python3
import sys

from manga_dialogue_pipeline.cli import main

raise SystemExit(main(["run", *sys.argv[1:]]))
