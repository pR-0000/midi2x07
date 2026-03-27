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
- `MUSIC_DATA_TEXT_BYTES`
- `MUSIC_DATA_PAYLOAD_BYTES`
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
MUSIC_DATA_TEXT_BYTES   equ 2166
MUSIC_DATA_PAYLOAD_BYTES equ 843
MUSIC_DATA_NAME_LEN     equ 9
music_data_name:        .db "music.mid",0
MUSIC_DATA_SIZE_TEXT_LEN equ 9
music_data_size_text:   .db "843 bytes",0
music_data:
    .db ...
```

Le nom du fichier MIDI source est tronqué de manière à conserver le suffixe `.mid` et à pouvoir s’afficher sur les lignes 2 et 3, jusqu’à environ 30 caractères selon la place laissée à l’indication de taille. La taille affichée dans le lecteur correspond à la taille réelle des données musicales encodées dans le programme, pas au MIDI d’origine ni à la taille texte du fichier `music_data.inc`.

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

### Référence des options

- `input_midi` : fichier MIDI source à convertir.
- `-o`, `--output` : fichier ASM généré. Par défaut : `music_data.inc`.
- `--bin-output` : export binaire brut optionnel du flux musical encodé.
- `--format auto|pair8|packed4` : choisit le format de sortie. `auto` garde le plus compact.
- `--unit-ms` : granularité temporelle. `50` est généralement le meilleur point de départ avec `ROM_BEEP`.
- `--min-note-units` : supprime les notes trop courtes.
- `--min-rest-units` : supprime les silences trop courts.
- `--merge-gap-units` : fusionne `NOTE + petit silence + même NOTE`.
- `--smooth-units` : lisse les micro-notes et micro-silences.
- `--track` : conserve seulement certaines pistes MIDI. Option répétable.
- `--channel` : conserve seulement certains canaux MIDI. Option répétable.
- `--include-drums` : inclut le canal batterie.
- `--priority highest|newest|melody` : stratégie de réduction monophonique.
- `--transpose` : transposition manuelle en demi-tons. Très utile si l’auto-transpose rend la musique trop aiguë.
- `--no-fold-octaves` : désactive le repli des notes hors plage par octaves.
- `--max-x07-note` : rabat les notes trop aiguës vers une ou plusieurs octaves plus basses.
- `--max-note-units` : coupe les notes trop longues en segments plus courts.
- `--retrigger-gap-units` : insère un petit silence entre les segments d’une note coupée.
- `--x07-groove` : réinjecte des impulsions simplifiées de basse et de percussion, mieux adaptées au buzzer.
- `--bass-pulse-units` : durée des impulsions de basse ajoutées par `--x07-groove`.
- `--bass-gap-units` : petit silence ajouté après chaque impulsion de basse pour mieux marquer le tempo.
- `--drum-pulse-units` : durée des impulsions de percussion ajoutées par `--x07-groove`.
- `--pseudo-poly 2` : illusion 2 voix par alternance rapide.
- `--pseudo-poly-step-units` : durée de chaque alternance en mode pseudo-polyphonique.

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
- si le MIDI source est déjà grave, essaye `--transpose 0` avant de laisser l’auto-transpose choisir une valeur trop haute
- `--x07-groove` est utile quand un MIDI contient déjà une basse et une batterie, mais que la réduction monophonique pure donne un rendu trop aigu ou trop pauvre
- avec `--x07-groove`, la ligne principale reste monophonique et le script réécrit seulement de très courtes impulsions graves de basse et de percussion
- `--bass-gap-units 1` est un bon point de départ pour éviter que la basse ne se transforme en note continue

Exemple de commande orientée “buzzer agréable” :

```powershell
python midi2x07.py music.mid --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1 --transpose 0 --max-x07-note 32 --x07-groove --include-drums
```

### Presets rapides

| Preset | Usage recommandé | Commande type |
| --- | --- | --- |
| `balanced` | Bon point de départ général | `python midi2x07.py music.mid --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1` |
| `low` | MIDI déjà grave ou rendu trop aigu | `python midi2x07.py music.mid --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1 --transpose 0 --max-x07-note 24` |
| `buzzer-friendly` | MIDI polyphonique avec basse/batterie à simplifier | `python midi2x07.py music.mid --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1 --transpose 0 --max-x07-note 32 --x07-groove --include-drums --bass-gap-units 1` |
| `compact` | Réduire au maximum la taille | `python midi2x07.py music.mid --format auto --unit-ms 100 --priority highest --merge-gap-units 2 --smooth-units 2 --max-x07-note 28` |

Repères rapides :

- `balanced` : à essayer en premier.
- `low` : utile si le résultat est trop strident.
- `buzzer-friendly` : utile si la version monophonique pure perd trop le rythme.
- `compact` : pratique pour des thèmes secondaires ou des jingles.

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
- `MUSIC_DATA_TEXT_BYTES`
- `MUSIC_DATA_PAYLOAD_BYTES`
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
MUSIC_DATA_TEXT_BYTES   equ 2166
MUSIC_DATA_PAYLOAD_BYTES equ 843
MUSIC_DATA_NAME_LEN     equ 9
music_data_name:        .db "music.mid",0
MUSIC_DATA_SIZE_TEXT_LEN equ 9
music_data_size_text:   .db "843 bytes",0
music_data:
    .db ...
```

The source MIDI filename is truncated so that the `.mid` suffix stays visible and the text can still fit across lines 2 and 3, up to about 30 characters depending on the byte-count text. The displayed size matches the actual encoded music payload stored in the program, not the original MIDI and not the text size of `music_data.inc`.

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

### Option reference

- `input_midi`: source MIDI file to convert.
- `-o`, `--output`: generated ASM file. Default: `music_data.inc`.
- `--bin-output`: optional raw binary export of the encoded music stream.
- `--format auto|pair8|packed4`: output format. `auto` keeps the smallest one.
- `--unit-ms`: time quantization. `50` is usually the best starting point with `ROM_BEEP`.
- `--min-note-units`: drop notes that are too short.
- `--min-rest-units`: drop rests that are too short.
- `--merge-gap-units`: merge `NOTE + short rest + same NOTE`.
- `--smooth-units`: smooth very short notes and rests.
- `--track`: keep only selected MIDI tracks. Repeatable.
- `--channel`: keep only selected MIDI channels. Repeatable.
- `--include-drums`: include the drum channel.
- `--priority highest|newest|melody`: monophonic reduction strategy.
- `--transpose`: manual transposition in semitones. Very useful when auto-transpose makes the result too bright.
- `--no-fold-octaves`: disable octave folding for out-of-range notes.
- `--max-x07-note`: fold overly bright notes down by one or more octaves.
- `--max-note-units`: split very long notes into shorter segments.
- `--retrigger-gap-units`: insert a small gap between split note segments.
- `--x07-groove`: reinject simplified bass and drum pulses that fit the buzzer better.
- `--bass-pulse-units`: duration of bass pulses added by `--x07-groove`.
- `--bass-gap-units`: small rest inserted after each bass pulse to keep the rhythm audible.
- `--drum-pulse-units`: duration of drum pulses added by `--x07-groove`.
- `--pseudo-poly 2`: fake 2 voices by fast alternation.
- `--pseudo-poly-step-units`: duration of each pseudo-poly alternation step.

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
- if the source MIDI already sits in a low register, try `--transpose 0` before relying on auto-transpose
- `--x07-groove` is useful when a MIDI already contains bass and drums, but pure monophonic reduction sounds too thin or too shrill
- with `--x07-groove`, the main line stays monophonic and the script only rewrites very short low bass and drum pulses
- `--bass-gap-units 1` is a good starting point if the bass starts to feel too continuous

Example of a more buzzer-friendly conversion:

```powershell
python midi2x07.py music.mid --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1 --transpose 0 --max-x07-note 32 --x07-groove --include-drums
```

### Quick presets

| Preset | Recommended use | Typical command |
| --- | --- | --- |
| `balanced` | Good general starting point | `python midi2x07.py music.mid --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1` |
| `low` | Source MIDI already sits low, or output sounds too bright | `python midi2x07.py music.mid --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1 --transpose 0 --max-x07-note 24` |
| `buzzer-friendly` | Polyphonic MIDI with bass/drums that needs buzzer-oriented simplification | `python midi2x07.py music.mid --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1 --transpose 0 --max-x07-note 32 --x07-groove --include-drums --bass-gap-units 1` |
| `compact` | Minimize data size as much as possible | `python midi2x07.py music.mid --format auto --unit-ms 100 --priority highest --merge-gap-units 2 --smooth-units 2 --max-x07-note 28` |

Quick hints:

- `balanced`: try this first.
- `low`: use this when the result sounds too shrill.
- `buzzer-friendly`: use this when pure monophonic reduction loses too much rhythm.
- `compact`: handy for secondary themes or short jingles.

### Limits

- monophonic output only
- the final result depends heavily on the quality of the source MIDI
- very polyphonic tracks usually need some tuning (`--priority`, `--smooth-units`, `--max-x07-note`)
