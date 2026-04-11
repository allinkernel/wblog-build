#!/usr/bin/zsh
source ~/.zshrc
set -x

if [[ ! -e out ]]; then
  mkdir -p out
fi

./generate_ninja.py "$(css)" "$(css)"/out/

/usr/bin/ninja -f out/build.ninja
