"""Basename → person attribution for camera and field-audio files."""

from __future__ import annotations

# Every camera proxy in the June and Aug 10 assemblies maps to exactly one person.
CAMERA_BASENAME_PERSON: dict[str, str] = {
    # June — 2026-05-27
    "A001_A001_0527UO_001.mov": "Kiki Redhead",
    "A001_A003_052701_001.mov": "Kiki Redhead",
    "B001_C001_01308G_001.mov": "Kiki Redhead",
    "B002_C002_01300X_001.mov": "Kiki Redhead",
    # June — 2026-06-09
    "A004C001_260609_R0DH.mov": "Jim Leonard",
    "A004C002_260609_R0DH.mov": "Stacy Conté",
    "A005C001_260609_R0DH.mov": "Stephanie Castro",
    "A006C001_260609_R0DH.mov": "Tony Rook",
    "B001C001_260609_R51N.mov": "Jim Leonard",
    "B001C002_260609_R51N.mov": "Stacy Conté",
    "B001C003_260609_R51N.mov": "Tony Rook",
    "B002C001_260609_R51N.mov": "Stephanie Castro",
    "B002C002_260609_R51N.mov": "Tony Rook",
    # June — 2026-06-10
    "A007C001_260610_R0DH.mov": "Morgan Sibbald",
    "A007C002_260610_R0DH.mov": "Tony Rook",
    "A007C003_260610_R0DH.mov": "Forrest Blackburn",
    "A008C001_260610_R0DH.mov": "Forrest Blackburn",
    "A008C002_260610_R0DH.mov": "Jim Leonard",
    "B003C001_260610_R51N.mov": "Morgan Sibbald",
    "B003C002_260610_R51N.mov": "Tony Rook",
    "B003C003_260610_R51N.mov": "Forrest Blackburn",
    "B004C001_260610_R51N.mov": "Forrest Blackburn",
    "B004C002_260610_R51N.mov": "Jim Leonard",
    # Aug 10 — stringout arithmetic (v02, CAM B)
    "B009C001_130101_R1IB.mov": "Chi Lee",
    "B010C001_130101_R1IB.mov": "Chi Lee",
    "B011C001_130101_R1IB.mov": "Destiny Thomas",
    "B012C001_130101_R1IB.mov": "Destiny Thomas",
    "B013C001_130101_R1IB.mov": "Caitlin Colleary",
    "B014C001_130101_R1IB.mov": "Caitlin Colleary",
    "B014C002_130101_R1IB.mov": "Nikki Burt",
    "B015C001_130101_R1IB.mov": "Miranda Sinnott-Armstrong",
    "B015C002_130101_R1IB.mov": "Miranda Sinnott-Armstrong",
    "B016C001_130101_R1IB.mov": "Emma Finestone",
    # Aug 10 — sync offsets (v03, CAM A)
    "A009C002_130101_R5DJ.mov": "Chi Lee",
    "A009C003_130101_R5DJ.mov": "Chi Lee",
    "A010C001_130101_R5DJ.mov": "Destiny Thomas",
    "A010C002_130101_R5DJ.mov": "Destiny Thomas",
    "A011C001_130101_R5DJ.mov": "Caitlin Colleary",
    "A012C001_130101_R5DJ.mov": "Caitlin Colleary",
    "A012C002_130101_R5DJ.mov": "Nikki Burt",
    "A013C001_120101_R5DJ.mov": "Miranda Sinnott-Armstrong",
    "A014C001_120101_R5DJ.mov": "Miranda Sinnott-Armstrong",
    "A015C001_130101_R5DJ.mov": "Emma Finestone",
}

# Field audio and lav-internal files keyed directly (not via frame ranges).
AUDIO_BASENAME_PERSON: dict[str, str] = {
    "Take 01 - Boom.wav": "Kiki Redhead",
    "Take 02 - Boom.wav": "Kiki Redhead",
    "Take 01 - Lav.wav": "Kiki Redhead",
    "Take 02 - Lav.wav": "Kiki Redhead",
    "Jim Leonard Take 01 Lav.WAV": "Jim Leonard",
    "Stacy Contii Take 01 Boom.wav": "Stacy Conté",
    "Stacy Contii Take 01 Lav.wav": "Stacy Conté",
    "Stephanie Castro Take 01 Boom.wav": "Stephanie Castro",
    "Stephanie Castro Take 01 Lav.wav": "Stephanie Castro",
    "Toni Rook Take 01 Boom.wav": "Tony Rook",
    "Toni Rook Take 01 Lav.wav": "Tony Rook",
    "Toni Rook (Redo) Boom.wav": "Tony Rook",
    "Toni Rook (Redo) Lav.wav": "Tony Rook",
    "Morgan Sibald Take 01 Boom.WAV": "Morgan Sibbald",
    "Morgan Sibald Take 01 Lav.WAV": "Morgan Sibbald",
    "Forest Blackburn Take 01 Boom.wav": "Forrest Blackburn",
    "Forest Blackburn Take 02 Boom.wav": "Forrest Blackburn",
    "Forest Blackburn Take 01 Lav.wav": "Forrest Blackburn",
    "Forest Blackburn Take 02 Lav.wav": "Forrest Blackburn",
    "Forest Blackburn Take 01.wav": "Forrest Blackburn",
    "Forest Blackburn Take 02.wav": "Forrest Blackburn",
    "Jim Leonard Boom.wav": "Jim Leonard",
    "Jim Leonard Lav.wav": "Jim Leonard",
    "20260610_2141_0146_32Float_3JN9.wav": "Morgan Sibbald",
    "20260610_2211_0147_32Float_3JN9.wav": "Morgan Sibbald",
    "20260610_2241_0148_32Float_3JN9.wav": "Morgan Sibbald",
    "20260610_2308_0150_32Float_3JN9.wav": "Tony Rook",
    "20260611_0221_0156_32Float_3JN9.wav": "Jim Leonard",
    # Aug 10 render lav (v02 A2)
    "Dr. Lee Take 01 Lav.wav": "Chi Lee",
    "Dr. Lee Take 02 Lav.wav": "Chi Lee",
    "Destiny Take 01 Boom.wav": "Destiny Thomas",
    "Destiny Take 02 Lav.wav": "Destiny Thomas",
    "Lav 03 Caitlin Take 01.wav": "Caitlin Colleary",
    "Caitlin Take 02 Lav.wav": "Caitlin Colleary",
    "Nicole Take 01 Lav.wav": "Nikki Burt",
    "Miranda Take 01 Lav.wav": "Miranda Sinnott-Armstrong",
    "Miranda Take 02 Lav.wav": "Miranda Sinnott-Armstrong",
    "Emma Lav.wav": "Emma Finestone",
    # Aug 10 boom (v03 B-keyed output paths)
    "Dr. Lee Take 01 Boom.wav": "Chi Lee",
    "Dr. Lee Take 02 Boom.wav": "Chi Lee",
    "Destiny Take 01 Boom.wav": "Destiny Thomas",
    "Destiny Take 02 Lav.wav": "Destiny Thomas",
    "Caitlin Take 01 Boom.wav": "Caitlin Colleary",
    "Caitlin Take 02 Boom.wav": "Caitlin Colleary",
    "Nicole Take 01 Boom.wav": "Nikki Burt",
    "Miranda Take 01 Boom.wav": "Miranda Sinnott-Armstrong",
    "Miranda Take 02 Boom.wav": "Miranda Sinnott-Armstrong",
    "Emma Boom.wav": "Emma Finestone",
}


def person_for_basename(basename: str) -> str:
    if basename in CAMERA_BASENAME_PERSON:
        return CAMERA_BASENAME_PERSON[basename]
    if basename in AUDIO_BASENAME_PERSON:
        return AUDIO_BASENAME_PERSON[basename]
    return "Unknown"


# One Premiere label colour per person (all tracks).
PERSON_LABEL_COLOR: dict[str, str] = {
    "Kiki Redhead": "Mango",
    "Jim Leonard": "Forest",
    "Stacy Conté": "Caribbean",
    "Stephanie Castro": "Cerulean",
    "Tony Rook": "Iris",
    "Morgan Sibbald": "Rose",
    "Forrest Blackburn": "Lavender",
    "Chi Lee": "Violet",
    "Destiny Thomas": "Cerulean",
    "Caitlin Colleary": "Mango",
    "Nikki Burt": "Iris",
    "Miranda Sinnott-Armstrong": "Rose",
    "Emma Finestone": "Lavender",
}


def label_color_for_person(person: str) -> str:
    return PERSON_LABEL_COLOR.get(person, "Forest")
