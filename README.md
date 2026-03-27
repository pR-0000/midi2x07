# midi2x07

## Français

`midi2x07` est un convertisseur `MIDI -> Canon X-07` qui génère des données musicales monophoniques pour des programmes Z80.

Le dossier contient :

- `midi2x07.py` : convertit un fichier `.mid` en `music_data.inc`
- `midi2x07.z80` : lecteur de démonstration autonome pour `ROM_BEEP`
- `midi2x07_irq.z80` : lecteur de démonstration autonome pour le driver IRQ custom
- `canon_x07.inc` : constantes et labels ROM utilisés par le lecteur

## Principe

Le script :

1. lit un fichier MIDI standard (`format 0` ou `1`)
2. réduit le contenu en monophonie
3. simplifie notes et silences
4. encode le résultat en `pair8` ou `packed4`
5. génère un include ASM standard appelé `music_data.inc`

Le point important est qu’il sait maintenant viser **deux drivers différents** :

- `--driver beep`
  - pour `ROM_BEEP`
  - notes converties dans la plage musicale X-07 `1..48`
  - fonctionne bien avec `unit-ms=50`
  - compatible avec le lecteur de démonstration `midi2x07.z80`
- `--driver irq`
  - pour un driver custom plus fin, piloté par interruptions
  - timings plus précis, donc `unit-ms=5`, `10` ou `20` deviennent réalistes
  - les hauteurs sont stockées via une **table de diviseurs 16 bits**
  - la plage utile descend plus bas que `ROM_BEEP`

Le format n’est donc **pas totalement différent** de celui utilisé par `ROM_BEEP` :

- le flux principal reste en `pair8` ou `packed4`
- ce qui change surtout, c’est le **sens de l’octet de note**

En mode `beep` :

- l’octet de note est une note X-07 directe (`1..48`)

En mode `irq` :

- l’octet de note est un **index de table**
- `music_pitch_table` contient les diviseurs 16 bits correspondant aux notes réellement utilisées
- les durées sont préconverties en ticks d’interruption du générateur de baud

Cela permet de réutiliser les mêmes optimisations de simplification et de compression, tout en produisant des données mieux adaptées à un driver plus fin.

## Fichiers générés

Le fichier `music_data.inc` contient toujours :

- `MUSIC_DATA_DRIVER`
- `MUSIC_DATA_FORMAT`
- `MUSIC_DATA_UNIT_MS`
- `MUSIC_DATA_BEEP_TICKS`
- `MUSIC_DATA_SOURCE_BYTES`
- `MUSIC_DATA_TEXT_BYTES`
- `MUSIC_DATA_PAYLOAD_BYTES`
- `MUSIC_DATA_PITCH_COUNT`
- `music_pitch_table`
- `MUSIC_DATA_NAME_LEN`
- `music_data_name`
- `MUSIC_DATA_SIZE_TEXT_LEN`
- `music_data_size_text`
- `music_data`

Exemple de structure :

```asm
; generated from music.mid
MUSIC_DRIVER_BEEP      equ 0
MUSIC_DRIVER_IRQ       equ 1
MUSIC_FORMAT_PAIR8     equ 0
MUSIC_FORMAT_PACKED4   equ 1
MUSIC_DATA_DRIVER      equ MUSIC_DRIVER_IRQ
MUSIC_DATA_FORMAT      equ MUSIC_FORMAT_PAIR8
MUSIC_DATA_UNIT_MS     equ 10
MUSIC_DATA_BEEP_TICKS  equ 1
MUSIC_DATA_PAYLOAD_BYTES equ 912
MUSIC_DATA_PITCH_COUNT equ 23
music_pitch_table:
    .dw ...
music_data:
    .db ...
```

## Formats

### `pair8`

Format simple :

```asm
.db note,durée,note,durée,...,$FF
```

Avantages :

- facile à relire
- facile à déboguer
- toujours disponible

### `packed4`

Format plus compact :

- durées courtes `1/2/4/8` encodées sur un seul octet
- `$FC note durée8`
- `$FD note durée16_lo durée16_hi`
- `$FF` fin

Avantages :

- souvent plus petit

Limite importante en mode `irq` :

- `packed4` n’est disponible que si la table de hauteurs contient **48 notes distinctes ou moins**
- sinon le script bascule automatiquement vers `pair8` en mode `auto`

## Utilisation rapide

### Sortie `ROM_BEEP`

```powershell
python midi2x07.py music.mid --driver beep --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1
```

### Sortie fine pour driver IRQ

```powershell
python midi2x07.py music.mid --driver irq --format auto --unit-ms 10 --priority melody --merge-gap-units 1 --smooth-units 1
```

## Assemblage et chargement

Il est recommandé d’assembler le lecteur de démonstration avec `sjasmplus`.

Exemple :

```powershell
sjasmplus.exe --raw=midi2x07.bin midi2x07.z80
```

Exemple pour le lecteur IRQ :

```powershell
sjasmplus.exe --raw=midi2x07_irq.bin midi2x07_irq.z80
```

Le lecteur de démonstration est prévu pour être injecté à l’adresse `0x2000`. L’utilisation de ce loader série par câble est recommandée :

[Canon X-07 Serial Fast Loader](https://github.com/pR-0000/Canon-X-07-Serial-Fast-Loader)

Important :

- `midi2x07.z80` ne lit que les données `--driver beep`
- `midi2x07_irq.z80` ne lit que les données `--driver irq`
- si `music_data.inc` a été généré avec le mauvais driver pour le lecteur choisi, l’assemblage échouera avec une erreur explicite

Le lecteur IRQ reprend globalement les mêmes fonctions que le lecteur `ROM_BEEP`, mais évite volontairement `ON/BREAK` pour la sortie afin de rester compatible avec le hook IRQ série. Il ajoute aussi une petite animation 8x8 en haut à gauche, dessinée directement en mémoire écran, pour montrer que la lecture continue pendant que le programme reste réactif. La vitesse courante est affichée en haut à droite (`x.5`, `x1`, `x2`).

## Écran du lecteur de démonstration

Le lecteur affiche :

- ligne 1 : `midi2x07` centré
- ligne 2 : le nom du fichier MIDI lu
- ligne 3 : la fin éventuelle du nom, puis `XXXXX bytes` en fin de ligne
- ligne 4 : l’état courant (`- Playing -` ou `- Paused -`)

Commandes :

- `F6` : pause / reprise
- `gauche` : redémarre la lecture depuis le début
- `droite` : active ou désactive l’animation
- `haut` : accélère la lecture
- `bas` : ralentit la lecture
- `SPACE` : quitte le programme

## Référence des options

- `input_midi` : fichier MIDI source à convertir
- `--list-tracks` : liste les pistes détectées, puis quitte
- `-o`, `--output` : fichier ASM généré, par défaut `music_data.inc`
- `--bin-output` : export binaire brut du flux d’événements
- `--driver beep|irq` : choisit le type de player visé
- `--format auto|pair8|packed4` : choisit le format du flux d’événements
- `--unit-ms` : granularité temporelle
- `--min-note-units` : supprime les notes trop courtes
- `--min-rest-units` : supprime les silences trop courts
- `--merge-gap-units` : fusionne `NOTE + petit silence + même NOTE`
- `--smooth-units` : lisse les micro-notes et micro-silences
- `--track` : conserve seulement certaines pistes MIDI
- `--prefer-track` : favorise certaines pistes lorsqu’il y a chevauchement
- `--exclude-track` : exclut certaines pistes MIDI
- `--channel` : conserve seulement certains canaux MIDI
- `--exclude-channel` : exclut certains canaux MIDI
- `--include-drums` : inclut le canal batterie
- `--priority highest|newest|melody` : stratégie de réduction monophonique
- `--transpose` : transposition manuelle en demi-tons
- `--no-fold-octaves` : désactive le repli par octaves
- `--max-x07-note` : limite les aigus en mode `beep`
- `--max-irq-midi` : limite les aigus en mode `irq`
- `--max-note-units` : coupe les notes trop longues
- `--retrigger-gap-units` : insère un petit silence entre segments d’une note coupée
- `--x07-groove` : réinjecte une basse et des percussions simplifiées
- `--bass-pulse-units` : durée des impulsions de basse
- `--bass-gap-units` : petit silence après chaque impulsion de basse
- `--drum-pulse-units` : durée des impulsions de percussion
- `--pseudo-poly 2` : illusion 2 voix par alternance rapide
- `--pseudo-poly-step-units` : durée de chaque alternance pseudo-polyphonique

Pour l’aide complète :

```powershell
python midi2x07.py -h
```

Pour lister les pistes d’un MIDI avant conversion :

```powershell
python midi2x07.py music.mid --list-tracks
```

## Conseils pratiques

- avec `ROM_BEEP`, `unit-ms=50` est le meilleur point de départ
- avec le driver `irq`, commence plutôt par `unit-ms=10`
- si le MIDI source est déjà grave, essaye `--transpose 0`
- si le résultat est trop strident en mode `beep`, baisse `--max-x07-note`
- si le résultat est trop strident en mode `irq`, baisse `--max-irq-midi`
- si une basse prend trop le dessus, utilise `--exclude-track`
- si tu veux favoriser un instrument sans supprimer les autres, utilise `--prefer-track`
- `--x07-groove` aide souvent les MIDIs complexes à garder un tempo plus lisible
- `--bass-gap-units 1` est un bon point de départ pour éviter l’effet “note grave continue”

Exemple `beep` agréable :

```powershell
python midi2x07.py music.mid --driver beep --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1 --transpose 0 --max-x07-note 32 --x07-groove --include-drums
```

Exemple `irq` fin :

```powershell
python midi2x07.py music.mid --driver irq --format auto --unit-ms 10 --priority melody --merge-gap-units 1 --smooth-units 1 --transpose 0 --max-irq-midi 84 --x07-groove --include-drums
```

Exemple d’exclusion de basse :

```powershell
python midi2x07.py music.mid --driver beep --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1 --transpose 0 --max-x07-note 24 --exclude-track 3
```

Exemple de priorité sur une piste :

```powershell
python midi2x07.py music.mid --driver beep --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1 --transpose 0 --max-x07-note 24 --prefer-track 5
```

## Presets rapides

| Preset | Usage recommandé | Commande type |
| --- | --- | --- |
| `balanced` | Bon point de départ général pour `ROM_BEEP` | `python midi2x07.py music.mid --driver beep --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1` |
| `low` | MIDI déjà grave ou rendu trop aigu | `python midi2x07.py music.mid --driver beep --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1 --transpose 0 --max-x07-note 24` |
| `buzzer-friendly` | MIDI polyphonique avec basse/batterie à simplifier | `python midi2x07.py music.mid --driver beep --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1 --transpose 0 --max-x07-note 32 --x07-groove --include-drums --bass-gap-units 1` |
| `irq-fine` | Sortie plus fine pour driver custom | `python midi2x07.py music.mid --driver irq --format auto --unit-ms 10 --priority melody --merge-gap-units 1 --smooth-units 1 --transpose 0 --max-irq-midi 84` |
| `compact` | Réduire au maximum la taille | `python midi2x07.py music.mid --driver beep --format auto --unit-ms 100 --priority highest --merge-gap-units 2 --smooth-units 2 --max-x07-note 28` |

Repères rapides :

- `balanced` : à essayer en premier
- `low` : utile si le rendu est trop strident
- `buzzer-friendly` : utile si la version monophonique pure perd trop le rythme
- `irq-fine` : utile si tu as déjà un driver custom interrupt-driven
- `compact` : pratique pour des thèmes secondaires ou des jingles

## Limites

- sortie monophonique uniquement
- le rendu dépend fortement du MIDI source
- les morceaux très polyphoniques demandent souvent un peu de réglage
- `midi2x07.z80` ne sert que pour le mode `beep`

## English

`midi2x07` is a `MIDI -> Canon X-07` converter that generates monophonic music data for Z80 programs.

The folder contains:

- `midi2x07.py`: converts a `.mid` file into `music_data.inc`
- `midi2x07.z80`: standalone demo player for `ROM_BEEP`
- `midi2x07_irq.z80`: standalone demo player for the custom IRQ driver
- `canon_x07.inc`: ROM constants and labels used by the player

## Overview

The script:

1. reads a standard MIDI file (`format 0` or `1`)
2. reduces it to a monophonic stream
3. simplifies notes and rests
4. encodes the result as `pair8` or `packed4`
5. generates a standard ASM include named `music_data.inc`

The important point is that it now targets **two different playback drivers**:

- `--driver beep`
  - for `ROM_BEEP`
  - notes are converted into the X-07 musical range `1..48`
  - works best with `unit-ms=50`
  - compatible with the demo player `midi2x07.z80`
- `--driver irq`
  - for a finer custom interrupt-driven driver
  - supports much finer timing, so `unit-ms=5`, `10` or `20` are realistic
  - pitches are stored through a **16-bit divisor table**
  - reaches lower practical notes than `ROM_BEEP`

So the data format is **not completely different** from the old `ROM_BEEP` flow:

- the main event stream is still `pair8` or `packed4`
- what changes is mostly the **meaning of the note byte**

In `beep` mode:

- the note byte is a direct X-07 pitch (`1..48`)

In `irq` mode:

- the note byte is a **pitch-table index**
- `music_pitch_table` stores the 16-bit divisors actually used by the track
- durations are preconverted into baud-generator interrupt ticks

This keeps the same simplification and compression pipeline while producing data better suited to a finer custom player.

## Generated file

`music_data.inc` always contains:

- `MUSIC_DATA_DRIVER`
- `MUSIC_DATA_FORMAT`
- `MUSIC_DATA_UNIT_MS`
- `MUSIC_DATA_BEEP_TICKS`
- `MUSIC_DATA_SOURCE_BYTES`
- `MUSIC_DATA_TEXT_BYTES`
- `MUSIC_DATA_PAYLOAD_BYTES`
- `MUSIC_DATA_PITCH_COUNT`
- `music_pitch_table`
- `MUSIC_DATA_NAME_LEN`
- `music_data_name`
- `MUSIC_DATA_SIZE_TEXT_LEN`
- `music_data_size_text`
- `music_data`

## Formats

### `pair8`

Simple format:

```asm
.db note,duration,note,duration,...,$FF
```

Advantages:

- easy to inspect
- easy to debug
- always available

### `packed4`

More compact format:

- short durations `1/2/4/8` stored in one byte
- `$FC note dur8`
- `$FD note dur16_lo dur16_hi`
- `$FF` end

Important limit in `irq` mode:

- `packed4` is only available when the pitch table contains **48 distinct pitches or fewer**
- otherwise `auto` falls back to `pair8`

## Quick usage

### `ROM_BEEP` output

```powershell
python midi2x07.py music.mid --driver beep --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1
```

### Fine output for the IRQ driver

```powershell
python midi2x07.py music.mid --driver irq --format auto --unit-ms 10 --priority melody --merge-gap-units 1 --smooth-units 1
```

## Assembly and loading

It is recommended to assemble the demo player with `sjasmplus`.

Example:

```powershell
sjasmplus.exe --raw=midi2x07.bin midi2x07.z80
```

IRQ demo example:

```powershell
sjasmplus.exe --raw=midi2x07_irq.bin midi2x07_irq.z80
```

The demo player is meant to be injected at address `0x2000`. Using this serial cable loader is recommended:

[Canon X-07 Serial Fast Loader](https://github.com/pR-0000/Canon-X-07-Serial-Fast-Loader)

Important:

- `midi2x07.z80` only supports `--driver beep`
- `midi2x07_irq.z80` only supports `--driver irq`
- if `music_data.inc` was generated for the wrong driver, assembly will fail with a clear error

The IRQ demo keeps roughly the same features as the `ROM_BEEP` demo player, but intentionally avoids using `ON/BREAK` for quitting so it stays compatible with the serial IRQ hook. It also adds a small on-screen animated indicator to show that interrupt-driven playback is active while the program stays responsive.
The IRQ demo keeps roughly the same features as the `ROM_BEEP` demo player, but intentionally avoids using `ON/BREAK` for quitting so it stays compatible with the serial IRQ hook. It also adds a small 8x8 animation in the top-left corner, drawn directly into screen memory, to show that interrupt-driven playback is active while the program stays responsive. The current speed is shown in the top-right corner (`x.5`, `x1`, `x2`).

## Demo player screen

The demo player shows:

- line 1: centered `midi2x07`
- line 2: the MIDI filename
- line 3: the optional filename continuation plus `XXXXX bytes`
- line 4: current state (`- Playing -` or `- Paused -`)

Controls:

- `F6`: pause / resume
- `left`: restart from the beginning
- `right`: toggle the animation on or off
- `up`: increase playback speed
- `down`: decrease playback speed
- `SPACE`: quit the program

## Option reference

- `input_midi`: source MIDI file to convert
- `--list-tracks`: list detected tracks, then exit
- `-o`, `--output`: generated ASM file, default `music_data.inc`
- `--bin-output`: optional raw event-stream export
- `--driver beep|irq`: choose the target playback driver
- `--format auto|pair8|packed4`: choose the event stream format
- `--unit-ms`: time quantization
- `--min-note-units`: drop notes shorter than this
- `--min-rest-units`: drop rests shorter than this
- `--merge-gap-units`: merge `NOTE + short rest + same NOTE`
- `--smooth-units`: smooth very short notes and rests
- `--track`: keep only selected MIDI tracks
- `--prefer-track`: prefer selected MIDI tracks during note overlap
- `--exclude-track`: exclude selected MIDI tracks
- `--channel`: keep only selected MIDI channels
- `--exclude-channel`: exclude selected MIDI channels
- `--include-drums`: include drum channel
- `--priority highest|newest|melody`: monophonic reduction strategy
- `--transpose`: manual semitone transpose
- `--no-fold-octaves`: disable octave folding
- `--max-x07-note`: tame high notes in `beep` mode
- `--max-irq-midi`: tame high notes in `irq` mode
- `--max-note-units`: split very long notes
- `--retrigger-gap-units`: insert a small rest between split segments
- `--x07-groove`: reinject simplified bass and drum pulses
- `--bass-pulse-units`: bass pulse duration
- `--bass-gap-units`: short rest after each bass pulse
- `--drum-pulse-units`: drum pulse duration
- `--pseudo-poly 2`: fake 2 voices by fast alternation
- `--pseudo-poly-step-units`: alternation step duration

Full help:

```powershell
python midi2x07.py -h
```

List tracks before converting:

```powershell
python midi2x07.py music.mid --list-tracks
```

## Practical tips

- with `ROM_BEEP`, `unit-ms=50` is the best starting point
- with the `irq` driver, start with `unit-ms=10`
- if the source MIDI is already low, try `--transpose 0`
- if the result is too shrill in `beep` mode, lower `--max-x07-note`
- if the result is too shrill in `irq` mode, lower `--max-irq-midi`
- if a bass line dominates too much, use `--exclude-track`
- if you only want to push one instrument forward, try `--prefer-track`
- `--x07-groove` often helps complex MIDIs keep a clearer rhythm
- `--bass-gap-units 1` is a good starting point to avoid “continuous low drone” bass

Pleasant `beep` example:

```powershell
python midi2x07.py music.mid --driver beep --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1 --transpose 0 --max-x07-note 32 --x07-groove --include-drums
```

Fine `irq` example:

```powershell
python midi2x07.py music.mid --driver irq --format auto --unit-ms 10 --priority melody --merge-gap-units 1 --smooth-units 1 --transpose 0 --max-irq-midi 84 --x07-groove --include-drums
```

## Quick presets

| Preset | Recommended use | Typical command |
| --- | --- | --- |
| `balanced` | Good general starting point for `ROM_BEEP` | `python midi2x07.py music.mid --driver beep --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1` |
| `low` | Already-low MIDI or overly bright result | `python midi2x07.py music.mid --driver beep --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1 --transpose 0 --max-x07-note 24` |
| `buzzer-friendly` | Polyphonic MIDI with bass/drums to simplify | `python midi2x07.py music.mid --driver beep --format auto --unit-ms 50 --priority melody --merge-gap-units 1 --smooth-units 1 --transpose 0 --max-x07-note 32 --x07-groove --include-drums --bass-gap-units 1` |
| `irq-fine` | Finer output for a custom interrupt-driven player | `python midi2x07.py music.mid --driver irq --format auto --unit-ms 10 --priority melody --merge-gap-units 1 --smooth-units 1 --transpose 0 --max-irq-midi 84` |
| `compact` | Minimize size as much as possible | `python midi2x07.py music.mid --driver beep --format auto --unit-ms 100 --priority highest --merge-gap-units 2 --smooth-units 2 --max-x07-note 28` |

## Limits

- monophonic output only
- output quality depends heavily on the source MIDI
- very dense polyphonic tracks usually need some tuning
- `midi2x07.z80` is only meant for `beep` mode
