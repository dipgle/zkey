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

# Composer binary: the native engine's line protocol (--line). The legacy
# zkey-line is only a fallback for packages staged before the native binary
# shipped; it speaks the older 'm'+word / '=word' protocol.
ZKEY_LINE_BIN=${ZKEY_LINE_BIN:-}
ZKEY_PROTO=native
if [[ -z $ZKEY_LINE_BIN ]]; then
    for zkey_candidate in "$ZKEY_HOME/native/target/release/zkey-native" \
            "$ZKEY_HOME/target/release/zkey-native"; do
        if [[ -x $zkey_candidate ]]; then ZKEY_LINE_BIN=$zkey_candidate; break; fi
    done
fi
if [[ -z $ZKEY_LINE_BIN && -x $ZKEY_HOME/target/release/zkey-line ]]; then
    ZKEY_LINE_BIN=$ZKEY_HOME/target/release/zkey-line
    ZKEY_PROTO=legacy
fi
if [[ -z $ZKEY_LINE_BIN ]]; then
    printf 'zkey: không thấy zkey-native (cargo build --release --manifest-path native/Cargo.toml); Telex dòng lệnh tắt.\n' >&2
    return 1
fi
if [[ $ZKEY_PROTO == native && $ZKEY_TONE == c ]]; then
    coproc ZKEY_LINE { exec "$ZKEY_LINE_BIN" --line traditional; }
else
    coproc ZKEY_LINE { exec "$ZKEY_LINE_BIN" --line; }
fi
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
    # Machine-typed input (tmux send-keys, launchers, automation) arrives as one
    # write: more bytes are already queued while we handle this key. A person's
    # next key is not. Such a line stays exactly as typed until it is emptied
    # (Enter, Ctrl+U) — commands typed by programs must never be rewritten
    # (15/11: `git reset` inside a quoted --disallowedTools became `git rết`).
    [[ -z $READLINE_LINE ]] && ZKEY_LITERAL=
    if [[ -n ${ZKEY_LITERAL-} ]] || read -r -t 0 2>/dev/null; then
        ZKEY_LITERAL=1
        __zkey_plain "$key"; return
    fi
    if [[ $ZKEY_MODE == off ]] || { [[ $ZKEY_MODE == quoted ]] && ! __zkey_in_quotes "$left"; } \
            || [[ -z ${ZKEY_LINE[1]-} ]]; then
        __zkey_plain "$key"; return
    fi
    [[ $left =~ ([[:alpha:]]*)$ ]]
    local word=${BASH_REMATCH[1]} raw reply text
    local prefix=${left:0:${#left}-${#word}}
    # Part of an identifier/path/variable (`doc_max`, `$HOME`, `a/b`, `x=y`) or
    # an ALL-CAPS token (`ROOT`, `API`): never a Vietnamese word. Trade-off:
    # Vietnamese typed in all caps stays as typed.
    local before=${prefix: -1}
    if [[ -n $before && '_0123456789$={}/.:@%+~\-' == *"$before"* ]] \
            || [[ ${#word} -ge 1 && $word$key != *[[:lower:]]* ]]; then
        __zkey_plain "$key"; return
    fi
    # Keep the raw keys while the line is exactly what we left it as.
    if [[ -n ${ZKEY_TEXT-} && $word == "$ZKEY_TEXT" && $READLINE_LINE == "$ZKEY_SEEN" \
            && $READLINE_POINT == "$ZKEY_POINT" ]]; then
        raw=$ZKEY_RAW$key
    else
        raw=$word$key
    fi
    local request reply text
    if [[ $ZKEY_PROTO == legacy ]]; then request=$ZKEY_TONE$raw; else request=$raw; fi
    if printf '%s\n' "$request" >&"${ZKEY_LINE[1]}" 2>/dev/null \
            && IFS= read -r -t 1 -u "${ZKEY_LINE[0]}" reply && [[ -n $reply && $reply != '!' ]]; then
        text=${reply#=}   # legacy replies "=word"; --line replies the word
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
