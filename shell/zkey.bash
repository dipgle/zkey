# SPDX-License-Identifier: AGPL-3.0-or-later
# zkey Telex for the bash command line (readline). Characters appear at once;
# the word before the cursor is recomposed in READLINE_LINE itself.
#
#   source /mnt/data/projects/zkey/shell/zkey.bash      (in ~/.bashrc)
#
# Why here and not in the input method: terminals (VTE) refuse to let an input
# method read or edit text already sent, and cannot tell it when a password is
# being typed. Readline only edits the command line, so prompts that read
# secrets (sudo, `read -s`, ssh) never pass through this code.
#
# Modes (Alt+Z cycles): quoted (default: only inside '...' or "...", where
# Vietnamese text lives; commands/flags/paths stay as typed) -> all -> off.
# Results that are not a plausible Vietnamese syllable stay as typed.
# Typed text is never logged.

[[ $- == *i* ]] || return 0
[[ -n ${ZKEY_LOADED-} ]] && return 0

ZKEY_HOME=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ZKEY_MODE=${ZKEY_MODE:-quoted}   # quoted | all | off
ZKEY_TONE=${ZKEY_TONE:-m}        # m = modern (hoà), c = classic (hòa)
ZKEY_ERRORS=0

if [[ ! -x $ZKEY_HOME/target/release/zkey-line ]]; then
    printf 'zkey: %s chưa được build (cargo build --release); Telex dòng lệnh tắt.\n' \
        "$ZKEY_HOME/target/release/zkey-line" >&2
    return 1
fi
coproc ZKEY_LINE { exec "$ZKEY_HOME/target/release/zkey-line"; }
ZKEY_LOADED=1

__zkey_in_quotes() {
    local s=$1 q= c i
    for ((i = 0; i < ${#s}; i++)); do
        c=${s:i:1}
        if [[ -z $q ]]; then
            if [[ $c == '\' ]]; then i=$((i + 1)); continue; fi
            [[ $c == '"' || $c == "'" ]] && q=$c
        elif [[ $q == '"' ]]; then
            if [[ $c == '\' ]]; then i=$((i + 1)); continue; fi
            [[ $c == '"' ]] && q=
        elif [[ $c == "'" ]]; then
            q=
        fi
    done
    [[ -n $q ]]
}

__zkey_plain() {  # insert the key as typed
    READLINE_LINE=${READLINE_LINE:0:READLINE_POINT}$1${READLINE_LINE:READLINE_POINT}
    READLINE_POINT=$((READLINE_POINT + 1))
    ZKEY_TEXT=
}

__zkey_key() {
    local key=$1 left=${READLINE_LINE:0:READLINE_POINT} right=${READLINE_LINE:READLINE_POINT}
    if [[ $ZKEY_MODE == off ]] || { [[ $ZKEY_MODE == quoted ]] && ! __zkey_in_quotes "$left"; } \
            || [[ -z ${ZKEY_LINE[1]-} ]]; then
        __zkey_plain "$key"; return
    fi
    [[ $left =~ ([[:alpha:]]*)$ ]]
    local word=${BASH_REMATCH[1]} raw reply text
    local prefix=${left:0:${#left}-${#word}}
    # Keep the raw keys while the line is exactly what we left it as.
    if [[ -n ${ZKEY_TEXT-} && $word == "$ZKEY_TEXT" && $READLINE_LINE == "$ZKEY_SEEN" \
            && $READLINE_POINT == "$ZKEY_POINT" ]]; then
        raw=$ZKEY_RAW$key
    else
        raw=$word$key
    fi
    if printf '%s%s\n' "$ZKEY_TONE" "$raw" >&"${ZKEY_LINE[1]}" 2>/dev/null \
            && IFS= read -r -t 1 -u "${ZKEY_LINE[0]}" reply && [[ $reply == =* ]]; then
        text=${reply:1}
    else
        ZKEY_ERRORS=$((ZKEY_ERRORS + 1))   # visible via zkey-status; key still typed
        __zkey_plain "$key"; return
    fi
    READLINE_LINE=$prefix$text$right
    READLINE_POINT=$((${#prefix} + ${#text}))
    ZKEY_RAW=$raw ZKEY_TEXT=$text ZKEY_SEEN=$READLINE_LINE ZKEY_POINT=$READLINE_POINT
}

__zkey_cycle() {
    case $ZKEY_MODE in quoted) ZKEY_MODE=all ;; all) ZKEY_MODE=off ;; *) ZKEY_MODE=quoted ;; esac
    printf '\nzkey: chế độ %s\n' "$ZKEY_MODE"
}

zkey-status() {
    local alive=no
    [[ -n ${ZKEY_LINE_PID-} ]] && kill -0 "$ZKEY_LINE_PID" 2>/dev/null && alive=yes
    printf 'zkey: mode=%s tone=%s service=%s errors=%d\n' "$ZKEY_MODE" "$ZKEY_TONE" "$alive" "$ZKEY_ERRORS"
}

for __zkey_c in {a..z} {A..Z}; do
    bind -x "\"$__zkey_c\": __zkey_key $__zkey_c"
done
unset __zkey_c
bind -x '"\ez": __zkey_cycle'
bind -x '"\eZ": __zkey_cycle'
