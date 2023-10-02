#!/bin/bash
set -e
DELAY="${DELAY:-10}"
LOOP="${LOOP:-0}"
r=`realpath "$1"`
d=`dirname "$r"`
pushd "$d" > /dev/null
f=`basename "$r"`
n=`webpinfo -summary "$f" | grep frames | sed -e 's/.* \([0-9]*\)$/\1/'`
dur=`webpinfo -summary "$f" | grep Duration | head -1 |  sed -e 's/.* \([0-9]*\)$/\1/'`

if (( "$dur" > 0 )); then
    DELAY="$dur"
fi

pfx=`echo -n $f | sed -e 's/^\(.*\).webp$/\1/'`
if [ -z "$pfx" ]; then
    pfx="$f"
fi

for i in $(seq -f "%05g" 1 "$n")
do
    webpmux -get frame "$i" "$f" -o "$pfx"."$i".webp >/dev/null 2>&1
    dwebp -quiet "$pfx"."$i".webp -o "$pfx"."$i".png
done

convert "$pfx".*.png -delay "$DELAY" -loop "$LOOP" "$pfx".gif >/dev/null 2>&1
realpath "$pfx".gif
rm "$pfx".[0-9]*.png "$pfx".[0-9]*.webp
popd > /dev/null
exit
