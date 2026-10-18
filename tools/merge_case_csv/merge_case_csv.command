#!/bin/bash
# Optovue など、症例フォルダごとに分かれた CSV を 1 枚にまとめる（Mac ダブルクリック用）
# 使い方: このファイルを右クリック →「開く」。症例フォルダの親フォルダを選ぶ。
# 動作確認: ./merge_case_csv.command /path/to/parent
set -u

export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-$LANG}"

notify() {
  local message="$1"
  printf '%s\n' "$message"
  if [[ "$(uname -s)" == "Darwin" ]] && command -v osascript >/dev/null 2>&1; then
    /usr/bin/osascript - "$message" <<'APPLESCRIPT' >/dev/null 2>&1 || true
on run argv
  display dialog (item 1 of argv) buttons {"OK"} default button "OK" with title "CSVを1枚にまとめる"
end run
APPLESCRIPT
  fi
}

reveal_file() {
  local path="$1"
  if [[ "$(uname -s)" == "Darwin" ]] && [[ -e "$path" ]]; then
    /usr/bin/open -R "$path" >/dev/null 2>&1 || true
  fi
}

if [[ $# -ge 1 ]]; then
  if [[ ! -d "$1" ]]; then
    notify "フォルダが見つかりません: $1"
    exit 1
  fi
  ROOT="$(cd "$1" && pwd)"
else
  if ! command -v osascript >/dev/null 2>&1; then
    notify "フォルダ選択が使えません。ターミナルで次のように実行してください。
bash このファイル 親フォルダのパス"
    exit 1
  fi
  set +e
  ROOT="$(/usr/bin/osascript <<'APPLESCRIPT'
set theFolder to choose folder with prompt "症例フォルダが入っている親フォルダを選んでください（中のCSVは自動で探します）"
POSIX path of theFolder
APPLESCRIPT
)"
  choose_status=$?
  set -e
  if [[ $choose_status -ne 0 || -z "${ROOT}" ]]; then
    printf '%s\n' "キャンセルしました。"
    exit 0
  fi
  ROOT="${ROOT%$'\r'}"
  ROOT="${ROOT%/}"
fi

PERL_BIN="/usr/bin/perl"
if [[ ! -x "$PERL_BIN" ]]; then
  PERL_BIN="$(command -v perl || true)"
fi
if [[ -z "$PERL_BIN" ]]; then
  notify "このMacでは perl が見つかりません。ターミナルの表示を柳まで送ってください。"
  exit 1
fi

set +e
RESULT="$(
  "$PERL_BIN" - "$ROOT" <<'PERL'
use strict;
use warnings;
use Encode qw(decode encode FB_CROAK);
use File::Find;
use File::Spec;

my $root = $ARGV[0];
$root =~ s{/+$}{};
die "no root\n" unless defined $root && -d $root;
binmode STDOUT, ':encoding(UTF-8)';

sub u8 {
    my ($s) = @_;
    return '' if !defined $s || $s eq '';
    return $s if utf8::is_utf8($s);
    my $decoded = eval { decode('UTF-8', $s, FB_CROAK) };
    return $decoded if defined $decoded && !$@;
    return $s;
}

sub decode_file {
    my ($path) = @_;
    open my $fh, '<:raw', $path or die "open $path: $!";
    local $/;
    my $bytes = <$fh>;
    close $fh;
    $bytes = '' if !defined $bytes;
    if (length($bytes) >= 3 && substr($bytes, 0, 3) eq "\xEF\xBB\xBF") {
        $bytes = substr($bytes, 3);
        return decode('UTF-8', $bytes, FB_CROAK);
    }
    my $utf8 = eval { decode('UTF-8', $bytes, FB_CROAK) };
    return $utf8 if defined $utf8 && !$@;
    for my $name (qw(cp932 shiftjis)) {
        my $text = eval { decode($name, $bytes, FB_CROAK) };
        return $text if defined $text && !$@;
    }
    die "encoding";
}

sub parse_csv {
    my ($text) = @_;
    $text =~ s/\r\n/\n/g;
    $text =~ s/\r/\n/g;
    my @rows;
    my @field;
    my $cur = '';
    my $in_q = 0;
    my @chars = split //, $text;
    for (my $i = 0; $i < @chars; $i++) {
        my $c = $chars[$i];
        if ($in_q) {
            if ($c eq '"') {
                if ($i + 1 < @chars && $chars[$i + 1] eq '"') {
                    $cur .= '"';
                    $i++;
                } else {
                    $in_q = 0;
                }
            } else {
                $cur .= $c;
            }
        } elsif ($c eq '"') {
            $in_q = 1;
        } elsif ($c eq ',') {
            push @field, $cur;
            $cur = '';
        } elsif ($c eq "\n") {
            push @field, $cur;
            push @rows, [@field] unless row_empty(@field);
            @field = ();
            $cur = '';
        } else {
            $cur .= $c;
        }
    }
    if ($cur ne '' || @field) {
        push @field, $cur;
        push @rows, [@field] unless row_empty(@field);
    }
    return @rows;
}

sub row_empty {
    for my $v (@_) {
        return 0 if defined $v && $v =~ /\S/;
    }
    return 1;
}

sub skip_reason {
    my ($base) = @_;
    return 'hidden' if $base =~ /^\./;
    return 'excel-lock' if $base =~ /^~\$/;
    return 'merged-output' if $base =~ /^merged_optovue_/i;
    return 'parameter' if $base =~ /parameter/i;
    return 'manifest' if $base =~ /^manifest\.csv$/i;
    return 'derived' if $base =~ /_U2\.csv$/i || $base =~ /recheck/i || $base =~ /adopted/i;
    return '';
}

sub is_mnv_header {
    my ($header) = @_;
    my %have = map { $_ => 1 } @$header;
    return 1 if $have{'Subtype'} || $have{'Network Complexity Score'} || $have{'Maturity Index'};
    return 0;
}

my @candidates;
my @skipped;
find({
    wanted => sub {
        my $full = $File::Find::name;
        return if -d $full;
        my $base = $_;
        return unless $base =~ /\.csv$/i;
        my $why = skip_reason($base);
        if ($why) {
            push @skipped, [$full, $why];
            return;
        }
        push @candidates, $full;
    },
    no_chdir => 0,
}, $root);

@candidates = sort @candidates;

my @parsed;
my $mnv_count = 0;
for my $full (@candidates) {
    my $text;
    eval { $text = decode_file($full); };
    if ($@) {
        push @skipped, [$full, 'unreadable'];
        next;
    }
    my @rows = parse_csv($text);
    if (!@rows) {
        push @skipped, [$full, 'empty'];
        next;
    }
    my $header = shift @rows;
    my $mnv = is_mnv_header($header) ? 1 : 0;
    $mnv_count++ if $mnv;
    push @parsed, {
        path => $full,
        header => $header,
        rows => \@rows,
        mnv => $mnv,
    };
}

my @use = @parsed;
if ($mnv_count > 0) {
    @use = grep { $_->{mnv} } @parsed;
    for my $item (@parsed) {
        next if $item->{mnv};
        push @skipped, [$item->{path}, 'not-mnv'];
    }
}

if (!@use) {
    my $msg = @skipped
        ? "CSVは見つかりましたが、まとめられる解析CSVがありませんでした。"
        : "CSVが見つかりませんでした。症例フォルダが入っている親フォルダを選んでください。";
    print "ERR\t$msg\n";
    exit 2;
}

my @columns = ('CaseFolder', 'SourceCsv');
my %seen_col = map { $_ => 1 } @columns;
for my $item (@use) {
    for my $col (@{ $item->{header} }) {
        next if !defined $col || $col eq '';
        next if $seen_col{$col};
        $seen_col{$col} = 1;
        push @columns, $col;
    }
}

sub rel_to_root {
    my ($full) = @_;
    my $rel = File::Spec->abs2rel($full, $root);
    $rel =~ s{\\}{/}g;
    return u8($rel);
}

sub case_folder_of {
    my ($rel) = @_;
    my ($dir) = $rel =~ m{^(.*)/[^/]+$};
    return '' if !defined $dir || $dir eq '' || $dir eq '.';
    my ($top) = split /\//, $dir;
    return $top;
}

my @out_rows;
for my $item (@use) {
    my $rel = rel_to_root($item->{path});
    my $case = case_folder_of($rel);
    my %idx;
    for my $i (0 .. $#{ $item->{header} }) {
        my $name = $item->{header}[$i];
        next if !defined $name || $name eq '' || exists $idx{$name};
        $idx{$name} = $i;
    }
    for my $row (@{ $item->{rows} }) {
        my @line = ($case, $rel);
        for my $col (@columns) {
            next if $col eq 'CaseFolder' || $col eq 'SourceCsv';
            if (!exists $idx{$col}) {
                push @line, '';
                next;
            }
            my $v = $row->[ $idx{$col} ];
            push @line, defined $v ? $v : '';
        }
        push @out_rows, \@line;
    }
}

my @stamp = localtime;
my $stamp_s = sprintf(
    '%04d%02d%02d_%02d%02d%02d',
    $stamp[5] + 1900, $stamp[4] + 1, $stamp[3], $stamp[2], $stamp[1], $stamp[0]
);
my $out_dir = $root;
if (!-w $root) {
    my $desk = File::Spec->catdir($ENV{HOME} || '.', 'Desktop');
    $out_dir = $desk if -d $desk && -w $desk;
}
my $out_path = File::Spec->catfile($out_dir, "merged_optovue_${stamp_s}.csv");
my $dup = 2;
while (-e $out_path) {
    $out_path = File::Spec->catfile($out_dir, "merged_optovue_${stamp_s}_${dup}.csv");
    $dup++;
}

sub csv_escape {
    my ($v) = @_;
    $v = '' if !defined $v;
    if ($v =~ /[",\r\n]/) {
        $v =~ s/"/""/g;
        return qq{"$v"};
    }
    return $v;
}

open my $out, '>:raw', $out_path or die "write $out_path: $!";
print $out "\xEF\xBB\xBF";
print $out encode('UTF-8', join(',', map { csv_escape($_) } @columns) . "\r\n");
for my $row (@out_rows) {
    print $out encode('UTF-8', join(',', map { csv_escape($_) } @$row) . "\r\n");
}
close $out;

my $nfiles = scalar @use;
my $nrows = scalar @out_rows;
my $nskipped = scalar @skipped;
print "OK\t$out_path\t$nfiles\t$nrows\t$nskipped\n";
for my $item (@use) {
    print "IN\t" . rel_to_root($item->{path}) . "\n";
}
for my $sk (@skipped) {
    my $rel = eval { rel_to_root($sk->[0]) };
    $rel = $sk->[0] if !defined $rel || $rel eq '';
    print "SKIP\t$rel\t$sk->[1]\n";
}
exit 0;
PERL
)"

status=$?
set +e

first_line="${RESULT%%$'\n'*}"
kind="${first_line%%$'\t'*}"
rest="${first_line#*$'\t'}"

if [[ $status -ne 0 || "$kind" != "OK" ]]; then
  message="${rest:-CSVをまとめられませんでした。}"
  notify "$message"
  printf '%s\n' "$RESULT"
  exit 1
fi

IFS=$'\t' read -r out_path nfiles nrows nskipped <<<"$rest"
message="CSVを1枚にまとめました。
解析CSV: ${nfiles} ファイル
データ行: ${nrows}
保存先:
${out_path}

元のCSVは変更していません。このファイルを柳までご返送ください。"
if [[ "${nskipped:-0}" != "0" ]]; then
  message="${message}
（対象外として読み飛ばしたファイル: ${nskipped}）"
fi

printf '%s\n' "$RESULT"
notify "$message"
reveal_file "$out_path"
exit 0
