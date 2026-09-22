#!/usr/bin/env bash
# Render the demo video (customer-facing clip for the Fiverr gig):
#
#   trim + crop ............ drops the browser tab strip + taskbar, and the first ~1s
#                            which still showed an unrelated PDF viewer window
#   jump cut ............... removes the ~1s where the Windows clipboard history panel
#                            was on screen (it listed unrelated snippets)
#   privacy mask ........... a solid box over the Telegram chat list during the two
#                            Telegram shots (it lists unrelated private chats, including
#                            a Telegram login-code preview)
#   end card ............... brand + summary + music credit
#   subtitles .............. burned AFTER the concat: per-segment burn restarts the ASS
#                            clock, so anything after the cut would be off by the offset
#   music .................. CC BY track, faded in/out, mixed at 0.30
set -e
cd "$(dirname "$0")"

# Nothing here is hard-coded to one machine: set these three when you re-render.
#   FF_BIN  directory holding ffmpeg / ffprobe   (default: wherever ffmpeg is on PATH)
#   SRC     the screen recording to cut the demo from        (required)
#   WORK    scratch + output directory  (default: this script's own folder)
FF_BIN="${FF_BIN:-$(dirname "$(command -v ffmpeg || echo ./ffmpeg)")}"
FFMPEG="${FFMPEG:-$FF_BIN/ffmpeg}"
FFPROBE="${FFPROBE:-$FF_BIN/ffprobe}"
: "${SRC:?set SRC to the source screen recording, e.g. SRC=./recording.mp4}"
WORK="${WORK:-$(cd "$(dirname "$0")" && pwd)}"

A_START=2.5;  A_LEN=15.5       # source 2.50 -> 18.00
B_START=19.4; B_LEN=26.2746    # source 19.40 -> 45.6746
END_LEN=3.0
TOTAL=44.78

CROP="crop=3072:1618:0:210"
SCALE="scale=1920:-2:flags=lanczos"
PAD="pad=1920:1080:0:34:color=0x0B1220"
# left chat list of Telegram Web, only while the Telegram shots are on screen
MASK="drawbox=x=0:y=110:w=620:h=940:color=0x0B1220@1:t=fill:enable='between(t,28.7,31.2)+between(t,38.3,41.8)'"

ENC="-c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -r 30 -fps_mode cfr -an"

echo "== 1/5 segment A (no subtitles)"
"$FFMPEG" -y -v error -ss $A_START -i "$SRC" -t $A_LEN -vf "$CROP,$SCALE,$PAD" $ENC "$WORK/seg_a.mp4"

echo "== 2/5 segment B (no subtitles)"
"$FFMPEG" -y -v error -ss $B_START -i "$SRC" -t $B_LEN -vf "$CROP,$SCALE,$PAD" $ENC "$WORK/seg_b.mp4"

echo "== 3/5 end card"
"$FFMPEG" -y -v error \
  -f lavfi -i "color=c=0x0B1220:s=1920x1080:r=30:d=$END_LEN" \
  -vf "drawtext=fontfile=arialbd.ttf:textfile=end_title.txt:fontcolor=white:fontsize=56:x=(w-text_w)/2:y=(h-text_h)/2-70,drawtext=fontfile=arial.ttf:textfile=end_sub.txt:fontcolor=0xC9D4E0:fontsize=32:x=(w-text_w)/2:y=(h-text_h)/2+10,drawtext=fontfile=arial.ttf:textfile=end_credit.txt:fontcolor=0x6C7A8A:fontsize=20:x=(w-text_w)/2:y=h-70" \
  $ENC -t $END_LEN "$WORK/seg_end.mp4"

echo "== 4/5 concat"
printf "file '%s/seg_a.mp4'\nfile '%s/seg_b.mp4'\nfile '%s/seg_end.mp4'\n" "$WORK" "$WORK" "$WORK" > list.txt
"$FFMPEG" -y -v error -f concat -safe 0 -i list.txt -c copy "$WORK/video_silent.mp4"

echo "== 5/5 mask + burn subtitles over the whole timeline + music bed"
"$FFMPEG" -y -v error -i "$WORK/video_silent.mp4" -i "$WORK/music.ogg" -filter_complex \
  "[0:v]$MASK,ass=subs.ass:fontsdir=.[v];[1:a]atrim=0:$TOTAL,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=1.5,afade=t=out:st=41.8:d=3.0,volume=0.30[a]" \
  -map "[v]" -map "[a]" -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -r 30 -fps_mode cfr \
  -c:a aac -b:a 192k -ar 48000 -movflags +faststart "$WORK/demo-final.mp4"

echo
echo "== result"
"$FFPROBE" -v error -show_entries format=duration,size -show_entries stream=codec_type,codec_name,width,height,r_frame_rate -of default=noprint_wrappers=1 "$WORK/demo-final.mp4"
echo "== loudness (music-only bed: -21..-18 LUFS is comfortable)"
"$FFMPEG" -hide_banner -nostats -i "$WORK/demo-final.mp4" -af ebur128 -f null - 2>&1 | grep -E "^\s+(I|LRA|Peak):" | tail -3 || true
