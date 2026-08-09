#!/usr/bin/zsh
source ~/.zshrc
set -x

if [[ ! -e out ]]; then
  mkdir -p out
fi

./generate_ninja.py "$(css)" "$(css)"/out/

/usr/bin/ninja -f out/build.ninja


# TODO: 这部分后续加到ninja中
rm -rf out/dist/template
ln -s $(css)/template out/dist/template    
