#!/usr/bin/env bash
# ===========================================================
#  make_webm_loop.sh
#  Creates a stitched, faded, 10s-per-clip background.webm
#  Requires: ffmpeg 4.4+ (libvpx-vp9 support)
# ===========================================================

set -e

INPUT_DIR="public/videos"       # folder with source clips (.mp4/.mov/etc.)
TMP_DIR="temp_snippets"
OUT_FILE="public/videos/background_loop.webm"

DURATION=10      # seconds per clip
FADE=1           # crossfade duration in seconds
CRF=32           # compression quality (lower = better quality)
RES="-2:1080"    # scale: -2 keeps width divisible by 2

mkdir -p "$TMP_DIR"
rm -f "$TMP_DIR"/* "$TMP_DIR"/concat_list.txt

echo "🎬 Trimming first $DURATION s of each video from $INPUT_DIR ..."
for f in "$INPUT_DIR"/*.mov; do
  [ -e "$f" ] || continue
  base=$(basename "$f")
  echo "  ➜ $base"
  ffmpeg -y -i "$f" -t $DURATION -vf "scale=$RES" \
    -an -c:v libx264 -preset veryfast -crf 20 "$TMP_DIR/$base" >/dev/null 
2>&1
  echo "file '$PWD/$TMP_DIR/$base'" >> "$TMP_DIR/concat_list.txt"
done

echo "✨ Stitching with $FADE s cross-fades ..."
ffmpeg -y -f concat -safe 0 -i "$TMP_DIR/concat_list.txt" -filter_complex 
\
"xfade=transition=fade:duration=$FADE:offset=$(($DURATION - 
$FADE)),format=yuv420p" \
-c:v libvpx-vp9 -b:v 0 -crf $CRF -an "$OUT_FILE"

echo "✅ Done! Output → $OUT_FILE"
echo "   You can now reference it in your React code as: 
/videos/background_loop.webm"

