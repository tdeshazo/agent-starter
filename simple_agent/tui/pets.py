"""Define header companion pets, half-block pixel sprites, and persisted selection."""
from dataclasses import dataclass
from pathlib import Path
import re

from ..settings import load_settings, save_settings, settings_path as settings_path


PET_NAMES = (
    "frog",
    "rabbit",
    "cat",
    "octopus",
    "alien",
    "robot",
    "moth",
    "axolotl",
    "hermit-crab",
    "ghost",
    "snail",
    "mimic",
)
DEFAULT_PET = "frog"
PET_GAP = 2

_HALF_BLOCKS = {
    (False, False): " ",
    (True, False): "▀",
    (False, True): "▄",
    (True, True): "█",
}


@dataclass(frozen=True)
class Pet:
    """Half-block pixel-art definition for a terminal companion pet.

    Each pair of pixel rows packs into one terminal row using upper/lower/full
    block characters (``▀``, ``▄``, ``█``) with independent foreground and
    background colors so pixels render roughly square.
    """

    name: str
    label: str
    description: str
    pixels: tuple[str, ...]
    palette: dict[str, tuple[int, int, int]]
    mono_cutout: frozenset[str] = frozenset({"k"})

    @property
    def width(self) -> int:
        return len(self.pixels[0]) if self.pixels else 0

    @property
    def height(self) -> int:
        return len(self.pixels) // 2


PETS: dict[str, Pet] = {
    "frog": Pet(
        name="frog",
        label="Frog",
        description="lush green pond hopper",
        pixels=(
            "..lll......lll..",
            ".lwwwl....lwwwl.",
            ".lwkwlgggglwkwl.",
            ".gwwwggggggwwwg.",
            ".gggggggggggggg.",
            "ggppggggggggppgg",
            "ggggkggggggkgggg",
            ".ggggkkkkkkgggg.",
            "..ggbbbbbbbbgg..",
            ".gggbbbbbbbbggg.",
            ".dggbbbbbbbbggd.",
            ".ddggbbbbbbggdd.",
            ".dddggggggggddd.",
            "ddd.dd....dd.ddd",
        ),
        palette={
            "d": (0x22, 0x72, 0x3A),  # deep forest shadow and webbed feet
            "g": (0x4C, 0xB9, 0x50),  # frog green body
            "l": (0x84, 0xE2, 0x6A),  # bright lime eye ridges
            "w": (0xF8, 0xFA, 0xF2),  # eye sclera
            "k": (0x1B, 0x3B, 0x24),  # pupils and smile
            "p": (0xF2, 0x84, 0x96),  # rosy cheeks
            "b": (0xE8, 0xF3, 0xB4),  # pale cream belly
        },
    ),
    "rabbit": Pet(
        name="rabbit",
        label="Rabbit",
        description="fluffy long-eared hopper",
        pixels=(
            "...ff......ff...",
            "...fpf....fpf...",
            "...fpf....fpf...",
            "...fpf....fpf...",
            "...fffwwwwfff...",
            "..ffffffffffff..",
            "..ffkffffffkff..",
            "..ffkffnnffkff..",
            "..fppffffffppf..",
            "...sffwwwwffs...",
            "..sfffwwwwfffsf.",
            "..sfffwwwwfffswf",
            "..ssffffffffssf.",
            "...sss....sss...",
        ),
        palette={
            "w": (0xF8, 0xF5, 0xFC),  # soft cream highlight and chest puff
            "f": (0xD6, 0xCC, 0xE6),  # pearl-lavender fur
            "s": (0x9C, 0x90, 0xB8),  # muted lilac shadow and paws
            "p": (0xF4, 0x9A, 0xB8),  # pink inner ears and cheeks
            "n": (0xE8, 0x6A, 0x92),  # berry-pink nose
            "k": (0x22, 0x1D, 0x2E),  # dark eyes
        },
    ),
    "cat": Pet(
        name="cat",
        label="Cat",
        description="warm ginger purr machine",
        pixels=(
            "..o........o....",
            ".ooo......ooo...",
            ".opo......opo...",
            ".opoooddooopo...",
            ".oooodoodoooo...",
            ".ooekooookeoo...",
            "wooeooppooeoow..",
            ".oooooccooooo.d.",
            "..ddoccccodd..oo",
            "..ooccccccoo...o",
            "..ooccccccoo...o",
            "..dooccccood..oo",
            "..ddooooooodddo.",
            "...cc....cc.....",
        ),
        palette={
            "o": (0xF2, 0x99, 0x4A),  # ginger tabby fur
            "d": (0xC4, 0x62, 0x28),  # cinnamon stripes and shading
            "p": (0xF5, 0x8D, 0xA4),  # pink inner ears and nose
            "e": (0x4A, 0xDF, 0x9C),  # emerald eyes
            "k": (0x1E, 0x16, 0x14),  # espresso pupils
            "c": (0xFA, 0xE6, 0xBE),  # cream muzzle, bib, and paws
            "w": (0xD8, 0xA8, 0x7A),  # warm whisker accents
        },
    ),
    "octopus": Pet(
        name="octopus",
        label="Octopus",
        description="coral eight-armed thinker",
        pixels=(
            "....rrrrrrrr....",
            "...rhhrrrrrrr...",
            "..rhhrrrrrrrrr..",
            "..rhrrrrrrrrrr..",
            "..rrwkrrrrwkrr..",
            "..rrkkrrrrkkrr..",
            "..rrhhrrrrhhrr..",
            "...ddrrrrrrdd...",
            "..rrrrrrrrrrrr..",
            ".rrrddrrrrddrrr.",
            ".rr.rrr..rrr.rr.",
            "rs..rrd..drr..sr",
            "rr...rr..rr...rr",
            ".d...ds..sd...d.",
        ),
        palette={
            "h": (0xFF, 0x9E, 0xB2),  # glossy dome highlight and cheeks
            "r": (0xE8, 0x56, 0x76),  # coral-rose mantle and tentacles
            "d": (0xB0, 0x2E, 0x52),  # deep berry shading
            "s": (0xFF, 0xD2, 0xDE),  # pale pink suckers
            "w": (0xFA, 0xFA, 0xFC),  # eye catchlights
            "k": (0x1F, 0x16, 0x26),  # dark glossy eyes
        },
    ),
    "alien": Pet(
        name="alien",
        label="Alien",
        description="mint-aqua cosmic visitor",
        pixels=(
            "...y........y...",
            "....a......a....",
            "....llaaaall....",
            "..llaaaaaaaall..",
            ".laawkkaakkwaal.",
            ".laakkkaakkkaal.",
            "..aaakkaakkaaa..",
            "...aaaaddaaaa...",
            "....ddaaaadd....",
            "...vvvvvvvvvv...",
            "..avvvvyyvvvva..",
            "..avuvvvvvvuva..",
            "...uuuvvvvuuu...",
            "....uu....uu....",
        ),
        palette={
            "y": (0xFF, 0xD8, 0x4D),  # glowing antenna orbs and chest badge
            "l": (0x8C, 0xF5, 0xDC),  # bright aqua highlight
            "a": (0x38, 0xCE, 0xAC),  # martian mint-teal skin
            "d": (0x1E, 0x8A, 0x78),  # deep teal shadow
            "k": (0x16, 0x18, 0x26),  # glossy almond eyes
            "w": (0xFA, 0xFC, 0xFF),  # eye sparkles
            "v": (0x7B, 0x5C, 0xE6),  # cosmic violet space suit
            "u": (0x4A, 0x34, 0x9C),  # indigo suit trim and boots
        },
    ),
    "robot": Pet(
        name="robot",
        label="Robot",
        description="steel-blue retro automaton",
        pixels=(
            ".......rr.......",
            ".......dd.......",
            "..hhhhhhhhhhhh..",
            "..mkkkkkkkkkkm..",
            ".dmkkcckkcckkmd.",
            ".dmkkcckkcckkmd.",
            "..mkkkkkkkkkkm..",
            "..dddddddddddd..",
            ".....dddddd.....",
            ".dmmhhhhhhhhmmd.",
            ".dmmmkcyyckmmmd.",
            ".d.mmkcccckmm.d.",
            "...ddmmmmmmdd...",
            "...ddd....ddd...",
        ),
        palette={
            "r": (0xFF, 0x5A, 0x6E),  # glowing coral antenna beacon
            "h": (0xC4, 0xD8, 0xEA),  # brushed silver highlight
            "m": (0x7E, 0x9B, 0xB8),  # cool steel-blue chassis
            "d": (0x46, 0x5B, 0x75),  # slate bolts, neck, and boots
            "k": (0x16, 0x20, 0x30),  # recessed dark visor and core housing
            "c": (0x38, 0xE8, 0xFF),  # glowing cyan LED eyes and core
            "y": (0xFF, 0xC8, 0x45),  # amber chest status light
        },
    ),
    "moth": Pet(
        name="moth",
        label="Moth",
        description="Convinced the terminal cursor is a porch light",
        pixels=(
            ".a.a........a.a.",
            "..aaa......aaa..",
            "....a.ssss.a....",
            "....swksskws....",
            "...fskkffkksf...",
            "..ffffsffsffff..",
            "..lssffffffssl..",
            ".llvvvddddvvvll.",
            ".lvvvvdvvdvvvvl.",
            ".lvvyyvddvyyvvl.",
            ".dvvvvvddvvvvvd.",
            "..dvvvl..lvvvd..",
            "..ddvv....vvdd..",
            "...dd......dd...",
        ),
        palette={
            "a": (0xE0, 0xB0, 0x6A),  # feathery golden-tan antennae
            "f": (0xF5, 0xEC, 0xDC),  # plush fuzzy cream collar
            "s": (0xCF, 0xBE, 0xAA),  # warm taupe head and collar shadow
            "k": (0x1E, 0x18, 0x2A),  # glossy dark moth eyes
            "w": (0xFA, 0xFC, 0xFF),  # eye catchlights
            "l": (0xC6, 0xB2, 0xF2),  # pale lilac wing highlight
            "v": (0x9C, 0x7E, 0xDC),  # folded lavender wings
            "d": (0x6B, 0x4E, 0xAD),  # twilight-violet wing fold and tips
            "y": (0xF8, 0xD4, 0x78),  # warm porch-light gold wing spots
        },
    ),
    "axolotl": Pet(
        name="axolotl",
        label="Axolotl",
        description="Greets every development with the same serene smile",
        pixels=(
            ".m............m.",
            "..g.hhhhhhhh.g..",
            "..ggppppppppgg..",
            "...pppppppppp...",
            "mggpkppppppkpggm",
            ".g.pkppppppkp.g.",
            "...pppkppkppp...",
            "mg.ppppkkpppp.gm",
            "..ggsppppppsgg..",
            "....ssbbbbss....",
            "...sppbbbbpps...",
            "..spppbbbbppps..",
            "..ssppppppppss..",
            "...ss......ss...",
        ),
        palette={
            "g": (0xE8, 0x4E, 0x8A),  # rose-magenta gill fronds
            "m": (0xC0, 0x2C, 0x68),  # deep magenta gill tips
            "h": (0xFF, 0xD2, 0xE2),  # soft cotton-candy head highlight
            "p": (0xFA, 0xA8, 0xC6),  # broad blush-pink face and body
            "s": (0xD8, 0x76, 0x9A),  # dusty-rose shading and feet
            "k": (0x2A, 0x18, 0x24),  # wide-set eyes and serene smile
            "b": (0xFF, 0xE6, 0xEE),  # pale cream-pink belly
        },
    ),
    "hermit-crab": Pet(
        name="hermit-crab",
        label="Hermit Crab",
        description="Moves house whenever it finds a nicer mug",
        pixels=(
            "...cc..ccccc....",
            "..cwwc.wwwwwc...",
            "..cwwwwwwwwwccc.",
            "..ctttttttttc.cc",
            "..cwwwwwwwwwc..c",
            "..cwwwwwwwwwc.cc",
            "..scccccccccscc.",
            "..ssddddddss....",
            "..rrwkrrkwrr....",
            ".llrrrrrrrrll...",
            "l.lrrddddrrl.l..",
            "ll.rrrrrrrr.ll..",
            ".dr.rr..rr.rd...",
            ".d..d....d..d...",
        ),
        palette={
            "w": (0xEA, 0xE2, 0xD3),  # warm porcelain teacup body
            "c": (0xCF, 0xC4, 0xB0),  # teacup rim and handle
            "s": (0x92, 0x87, 0x78),  # stoneware under-rim shadow
            "t": (0x46, 0x95, 0xAA),  # vintage teal mug stripe
            "l": (0xF2, 0x6D, 0x4A),  # bright coral-rust claw highlight
            "r": (0xC9, 0x42, 0x2B),  # rust-red shell and claws
            "d": (0x84, 0x24, 0x18),  # deep burnt-rust shadow and legs
            "k": (0x1C, 0x14, 0x16),  # curious beady crab eyes
        },
    ),
    "ghost": Pet(
        name="ghost",
        label="Ghost",
        description="Tries to haunt the terminal but gets shy when noticed",
        pixels=(
            ".....bbbbbb.....",
            "...bbhhhhhhbb...",
            "..bhhwwwwwwbbs..",
            "..bwwwwwwkkwbs..",
            ".bhwwkkwwwkkbbs.",
            ".bwwwkkwwwwwbbs.",
            ".bwwppwwwwppbbs.",
            ".bwwwwwwwwwwbbs.",
            ".bbwwwwbwwwwbbs.",
            ".bbwwwbbwwwwbbs.",
            ".sbbwwbbwwwbbbs.",
            ".sbbb.bbbb.bbbs.",
            "..ss...ss...ss..",
            "................",
        ),
        palette={
            "h": (0xFF, 0xFF, 0xFF),  # crisp moonlight highlight
            "w": (0xDC, 0xE2, 0xF8),  # pale ghostly ice-lavender sheet
            "b": (0xA8, 0xB2, 0xDC),  # cool periwinkle drape shadow
            "s": (0x76, 0x7C, 0xAC),  # twilight-periwinkle hem contour
            "k": (0x16, 0x18, 0x26),  # deep midnight eyeholes
            "p": (0xF6, 0x98, 0xB8),  # shy rosy blush cheeks
        },
    ),
    "snail": Pet(
        name="snail",
        label="Snail",
        description="Takes its time and looks pleased about it",
        pixels=(
            "..hhhaaa........",
            ".hhhaaaaa.......",
            "hhaadddaaa.ww...",
            "aaadhhhdaa.wk.ww",
            "aadhaadada..b.wk",
            "aadhaaddaa..b.b.",
            "aaadhaaaoo..b.b.",
            ".aaaddddoo..b.b.",
            "..oooooooo.bbbb.",
            "...oooooobbbbbbb",
            ".bbbbbbbbbbpbbkb",
            "sbbbbbbbbbbbkkbb",
            "sssbbbbbbbbbbbs.",
            ".sssssssssssss..",
        ),
        palette={
            "h": (0xFF, 0xCF, 0x5C),  # glossy golden-amber highlight
            "a": (0xE6, 0x8A, 0x24),  # rich warm amber spiral shell
            "o": (0xB8, 0x5C, 0x14),  # deep honey-ochre shell shade
            "d": (0x6B, 0x32, 0x0E),  # dark chestnut spiral groove
            "b": (0xC6, 0xDA, 0xA8),  # soft sage-cream snail body
            "s": (0x7E, 0x9A, 0x68),  # mossy-sage creeping foot shadow
            "w": (0xF0, 0xEC, 0xDC),  # warm ivory eye sclera
            "k": (0x18, 0x16, 0x18),  # dark pupils and pleased smile
            "p": (0xF2, 0x94, 0x9E),  # pleased rosy cheek
        },
    ),
    "mimic": Pet(
        name="mimic",
        label="Mimic",
        description="Hoards loose semicolons",
        pixels=(
            "...lyllllllly...",
            "..lwywwwwwwywl..",
            "..wwgwwwwwwgww..",
            ".gggggggggggggg.",
            "..kkkkkkkkkkkk..",
            "..kkccekkecckk..",
            "..kkekckkckekk..",
            "..gggggggggggg..",
            "..wwgwwyywwgww..",
            "..wwgwwykwwgww..",
            "..ddgddddddgdd..",
            "..gggggggggggg..",
            "....ff....ff....",
            "...fff....fff...",
        ),
        palette={
            "l": (0xAA, 0x70, 0x28),  # warm oak lid highlight
            "w": (0x7E, 0x4A, 0x18),  # rich chestnut chest planks
            "d": (0x4A, 0x2A, 0x10),  # deep walnut shadow
            "y": (0xFF, 0xDE, 0x58),  # bright burnished gold gleam
            "g": (0xD4, 0x9A, 0x28),  # antique brass straps and trim
            "k": (0x16, 0x12, 0x18),  # shadowy chest interior and pupils
            "c": (0xFF, 0xFC, 0xF0),  # bright mischievous eye sclera
            "e": (0xFF, 0xC8, 0x3A),  # glowing golden mimic iris
            "f": (0xC4, 0x68, 0x82),  # stubby dusty-rose monster feet
        },
    ),
}


def normalize_pet(name: str | None) -> str | None:
    """Return a canonical pet name if valid, otherwise None."""
    if not isinstance(name, str):
        return None
    normalized = re.sub(r"[\s_]+", "-", name.strip().lower())
    return normalized if normalized in PETS else None


def load_pet(path: Path | None = None) -> str:
    """Load the persisted pet name, falling back to DEFAULT_PET on any issue."""
    return normalize_pet(load_settings(path).get("pet")) or DEFAULT_PET


def save_pet(pet: str, path: Path | None = None) -> str:
    """Validate and persist the chosen pet name across sessions."""
    canonical = normalize_pet(pet)
    if canonical is None:
        choices = ", ".join(PET_NAMES)
        raise ValueError(f"Unknown pet {pet!r}. Choose from: {choices}.")
    save_settings({"pet": canonical}, path)
    return canonical


def _cube_index(rgb: tuple[int, int, int]) -> int:
    r, g, b = (round(c / 255 * 5) for c in rgb)
    return 16 + 36 * r + 6 * g + b


def _color_code(rgb: tuple[int, int, int], *, background: bool, true_color: bool) -> str:
    """Return an SGR foreground or background color code."""
    prefix = 48 if background else 38
    if true_color:
        return f"{prefix};2;{rgb[0]};{rgb[1]};{rgb[2]}"
    return f"{prefix};5;{_cube_index(rgb)}"


def _same_rendered_color(
    top: tuple[int, int, int], bot: tuple[int, int, int], true_color: bool
) -> bool:
    if true_color:
        return top == bot
    return _cube_index(top) == _cube_index(bot)


def pet_width(pet: str = DEFAULT_PET) -> int:
    """Return the unstyled display column width of the given pet."""
    chosen = PETS[normalize_pet(pet) or DEFAULT_PET]
    return chosen.width


def pet_rows(pet: str = DEFAULT_PET, color: bool = True, *, true_color: bool = False) -> list[str]:
    """Render the chosen pet as half-block pixel art rows."""
    chosen = PETS[normalize_pet(pet) or DEFAULT_PET]
    rows: list[str] = []
    for y in range(0, len(chosen.pixels), 2):
        upper = chosen.pixels[y]
        lower = chosen.pixels[y + 1] if y + 1 < len(chosen.pixels) else "." * chosen.width
        cells: list[str] = []
        for top_key, bot_key in zip(upper, lower):
            top_rgb = chosen.palette.get(top_key)
            bot_rgb = chosen.palette.get(bot_key)
            if not color:
                top_on = top_rgb is not None and top_key not in chosen.mono_cutout
                bot_on = bot_rgb is not None and bot_key not in chosen.mono_cutout
                cells.append(_HALF_BLOCKS[(top_on, bot_on)])
                continue
            if top_rgb is None and bot_rgb is None:
                cells.append(" ")
            elif top_rgb is None:
                code = _color_code(bot_rgb, background=False, true_color=true_color)
                cells.append(f"\x1b[{code}m▄\x1b[0m")
            elif bot_rgb is None:
                code = _color_code(top_rgb, background=False, true_color=true_color)
                cells.append(f"\x1b[{code}m▀\x1b[0m")
            elif _same_rendered_color(top_rgb, bot_rgb, true_color):
                code = _color_code(top_rgb, background=False, true_color=true_color)
                cells.append(f"\x1b[{code}m█\x1b[0m")
            else:
                fg = _color_code(top_rgb, background=False, true_color=true_color)
                bg = _color_code(bot_rgb, background=True, true_color=true_color)
                cells.append(f"\x1b[{fg};{bg}m▀\x1b[0m")
        rows.append("".join(cells))
    return rows
