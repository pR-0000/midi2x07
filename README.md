# midi2x07

## Français

`midi2x07` est un petit convertisseur `MIDI -> Canon X-07` qui produit une musique monophonique lisible depuis un programme Z80.

Le dossier contient :

- `midi2x07.py` : convertit un fichier `.mid` en `music_data.inc`
- `midi2x07.z80` : lecteur de démonstration autonome pour X-07
- `canon_x07.inc` : constantes et labels ROM utilisés par le lecteur

### Principe

Le script :

1. lit un fichier MIDI standard (`format 0` ou `1`)
2. réduit le contenu en monophonie
3. simplifie les notes et les silences
4. encode le résultat en `pair8` ou `packed4`
5. génère un include ASM standard appelé `music_data.inc`

Le fichier généré contient toujours :

- le label `music_data`
- `MUSIC_DATA_FORMAT`
- `MUSIC_DATA_UNIT_MS`
- `MUSIC_DATA_BEEP_TICKS`
- `MUSIC_DATA_SOURCE_BYTES`
- `MUSIC_DATA_NAME_LEN`
- `music_data_name`
- `MUSIC_DATA_SIZE_TEXT_LEN`
- `music_data_size_text`

Le lecteur ASM peut donc s’adapter automatiquement au format généré.

### Formats

#### `pair8`

Format simple :

```asm
.db note,durée,note,durée,...,$FF
```

Avantages :

- facile à relire
- facile à déboguer
- lecteur ASM simple

#### `packed4`

Format plus compact :

- durées courtes `1/2/4/8` encodées sur un seul octet
- `$FC note durée8`
- `$FD note durée16_lo durée16_hi`
- `$FF` fin

Avantages :

- souvent plus petit en données

### Utilisation rapide

Depuis le dossier `midi2x07` :

```powershell
python midi2x07.py music.mid --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1
```

### Assemblage et chargement

Il est recommandé d’assembler le lecteur de démonstration avec `sjasmplus`.

Exemple :

```powershell
sjasmplus.exe --raw=midi2x07.bin midi2x07.z80
```

Le lecteur de démonstration est prévu pour être injecté à l’adresse `0x2000`. L’utilisation de ce loader série par câble est recommandé :

[Canon X-07 Serial Fast Loader](https://github.com/pR-0000/Canon-X-07-Serial-Fast-Loader)

### Sortie générée

Par défaut, le script produit `music_data.inc`.

Exemple de début de fichier :

```asm
; generated from music.mid
MUSIC_FORMAT_PAIR8      equ 0
MUSIC_FORMAT_PACKED4    equ 1
MUSIC_DATA_FORMAT       equ MUSIC_FORMAT_PAIR8
MUSIC_DATA_UNIT_MS      equ 50
MUSIC_DATA_BEEP_TICKS   equ 1
MUSIC_DATA_SOURCE_BYTES equ 26436
MUSIC_DATA_NAME_LEN     equ 9
music_data_name:        .db "music.mid",0
MUSIC_DATA_SIZE_TEXT_LEN equ 11
music_data_size_text:   .db "26436 bytes",0
music_data:
    .db ...
```

Le nom du fichier MIDI source est tronqué de manière à conserver le suffixe `.mid` et à pouvoir s’afficher sur les lignes 2 et 3, jusqu’à environ 30 caractères selon la place laissée à l’indication de taille.

### Lecteur ASM

`midi2x07.z80` inclut `music_data.inc` et utilise `MUSIC_DATA_FORMAT` pour choisir à l’assemblage :

- le décodeur `pair8`
- ou le décodeur `packed4`

Le binaire final ne contient donc que le code nécessaire au format réellement généré.

L’écran du lecteur de démonstration affiche :

- ligne 1 : `midi2x07` centré
- ligne 2 : le nom du fichier MIDI lu
- ligne 3 : la fin éventuelle du nom, puis `XXXXX bytes` en fin de ligne
- ligne 4 : l’état courant (`- Playing -` ou `- Paused -`)

Commandes du lecteur :

- `F6` : pause / reprise
- `gauche` : redémarre la lecture depuis le début
- `BREAK` : quitte le programme

### Réglages utiles

- `--format auto|pair8|packed4` : choix du format de sortie
- `--unit-ms` : granularité temporelle
- `--priority highest|newest|melody` : stratégie de réduction monophonique
- `--merge-gap-units` : fusionne de très petits silences
- `--smooth-units` : lisse micro-notes et micro-silences
- `--max-x07-note` : rabat les notes trop aiguës d’une ou plusieurs octaves
- `--max-note-units` : coupe les notes trop longues
- `--retrigger-gap-units` : petit silence entre segments d’une note coupée
- `--pseudo-poly 2` : illusion 2 voix par alternance rapide

Pour la liste complète :

```powershell
python midi2x07.py -h
```

### Conseils pratiques

- `unit_ms=50` est le meilleur point de départ avec `ROM_BEEP`
- des valeurs non multiples de `50 ms` restent possibles, mais seront approximées côté lecteur
- `packed4` est souvent meilleur pour la taille
- `pair8` est meilleur pour inspecter rapidement le résultat
- pour une musique plus agréable sur buzzer, il vaut souvent mieux limiter les notes trop aiguës

### Limites

- sortie monophonique uniquement
- le rendu dépend fortement de la qualité du MIDI source
- les morceaux très polyphoniques demandent souvent un peu de réglage (`--priority`, `--smooth-units`, `--max-x07-note`)

## English

`midi2x07` is a small `MIDI -> Canon X-07` converter that generates monophonic music data for Z80 programs.

The folder contains:

- `midi2x07.py`: converts a `.mid` file into `music_data.inc`
- `midi2x07.z80`: standalone demo player for the X-07
- `canon_x07.inc`: ROM constants and labels used by the player

### Overview

The script:

1. reads a standard MIDI file (`format 0` or `1`)
2. reduces it to a monophonic stream
3. simplifies notes and rests
4. encodes the result as `pair8` or `packed4`
5. generates a standard ASM include named `music_data.inc`

The generated file always contains:

- the `music_data` label
- `MUSIC_DATA_FORMAT`
- `MUSIC_DATA_UNIT_MS`
- `MUSIC_DATA_BEEP_TICKS`
- `MUSIC_DATA_SOURCE_BYTES`
- `MUSIC_DATA_NAME_LEN`
- `music_data_name`
- `MUSIC_DATA_SIZE_TEXT_LEN`
- `music_data_size_text`

This allows the ASM player to adapt automatically to the generated format.

### Formats

#### `pair8`

Simple format:

```asm
.db note,duration,note,duration,...,$FF
```

Advantages:

- easy to read
- easy to debug
- simple ASM decoder

#### `packed4`

More compact format:

- short durations `1/2/4/8` packed into one byte
- `$FC note dur8`
- `$FD note dur16_lo dur16_hi`
- `$FF` end marker

Advantages:

- often smaller in data size

### Quick usage

From the `midi2x07` folder:

```powershell
python midi2x07.py music.mid --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1
```

### Assembly and loading

It is recommended to assemble the demo player with `sjasmplus`.

Example:

```powershell
sjasmplus.exe --raw=midi2x07.bin midi2x07.z80
```

The demo player is meant to be injected at address `0x2000`. This serial cable loader is recommended to do so:

[Canon X-07 Serial Fast Loader](https://github.com/pR-0000/Canon-X-07-Serial-Fast-Loader)

### Generated output

By default, the script writes `music_data.inc`.

Example header:

```asm
; generated from music.mid
MUSIC_FORMAT_PAIR8      equ 0
MUSIC_FORMAT_PACKED4    equ 1
MUSIC_DATA_FORMAT       equ MUSIC_FORMAT_PAIR8
MUSIC_DATA_UNIT_MS      equ 50
MUSIC_DATA_BEEP_TICKS   equ 1
MUSIC_DATA_SOURCE_BYTES equ 26436
MUSIC_DATA_NAME_LEN     equ 9
music_data_name:        .db "music.mid",0
MUSIC_DATA_SIZE_TEXT_LEN equ 11
music_data_size_text:   .db "26436 bytes",0
music_data:
    .db ...
```

The source MIDI filename is truncated so that the `.mid` suffix stays visible and the text can still fit across lines 2 and 3, up to about 30 characters depending on the byte-count text.

### ASM player

`midi2x07.z80` includes `music_data.inc` and uses `MUSIC_DATA_FORMAT` at assembly time to keep only:

- the `pair8` decoder
- or the `packed4` decoder

So the final binary only contains the code required for the selected format.

The demo player screen shows:

- line 1: centered `midi2x07`
- line 2: source MIDI filename
- line 3: possible filename continuation, plus `XXXXX bytes` at the end of the line
- line 4: current state (`- Playing -` or `- Paused -`)

Player controls:

- `F6`: pause / resume
- `left`: restart playback from the beginning
- `BREAK`: quit the program

### Useful options

- `--format auto|pair8|packed4`: output format
- `--unit-ms`: time quantization
- `--priority highest|newest|melody`: monophonic reduction strategy
- `--merge-gap-units`: merges very short rests
- `--smooth-units`: smooths very short notes and rests
- `--max-x07-note`: folds overly high notes down by one or more octaves
- `--max-note-units`: splits notes that are too long
- `--retrigger-gap-units`: inserts a small gap between split note segments
- `--pseudo-poly 2`: fake 2-voice effect by fast alternation

For the full list:

```powershell
python midi2x07.py -h
```

### Practical notes

- `unit_ms=50` is the best starting point with `ROM_BEEP`
- values not aligned to `50 ms` are still possible, but playback will be approximated on the player side
- `packed4` is often better for size
- `pair8` is better for quickly inspecting the result
- to make buzzer playback more pleasant, it often helps to limit very high notes

### Limits

- monophonic output only
- the final result depends heavily on the quality of the source MIDI
- very polyphonic tracks usually need some tuning (`--priority`, `--smooth-units`, `--max-x07-note`)
