"""`python -m studylog` と PyInstaller の入口。

EXEにすると、このファイルはトップレベルのスクリプトとして実行される
（パッケージの一部ではなくなる）ため、相対importは使えない。
"""

from studylog.app import main

if __name__ == "__main__":
    raise SystemExit(main())
