/* Copyright (c) 2024-2025, CC BY-SA 4.0, Tremeschin */

#define WHITE_COLOR vec3(0.9)
#define BLACK_COLOR vec3(0.2)
#define PBAR_SIZE 0.015
#define TOP_BORDER 0.03
#define HORIZONTAL 0
#define VIGNETTE 0
#define BLEED 0.02
#define COLUMN_WIDTH 0.06

// Rainbow note colors: C=Red, D=Orange, E=Yellow, F=Green, G=Blue, A=Purple, B=Pink
vec3 getNoteColor(int noteIndex) {
    int pc = noteIndex % 12;
    vec3 color = vec3(0.5);
         if (pc == 0)  {color = vec3(0.93, 0.35, 0.35);}  // C  - Red
    else if (pc == 1)  {color = vec3(0.93, 0.35, 0.35);}  // C# - Red
    else if (pc == 2)  {color = vec3(0.96, 0.65, 0.25);}  // D  - Orange
    else if (pc == 3)  {color = vec3(0.96, 0.65, 0.25);}  // D# - Orange
    else if (pc == 4)  {color = vec3(0.95, 0.82, 0.25);}  // E  - Yellow
    else if (pc == 5)  {color = vec3(0.45, 0.78, 0.36);}  // F  - Green
    else if (pc == 6)  {color = vec3(0.45, 0.78, 0.36);}  // F# - Green
    else if (pc == 7)  {color = vec3(0.40, 0.58, 0.92);}  // G  - Blue
    else if (pc == 8)  {color = vec3(0.40, 0.58, 0.92);}  // G# - Blue
    else if (pc == 9)  {color = vec3(0.62, 0.42, 0.82);}  // A  - Purple
    else if (pc == 10) {color = vec3(0.62, 0.42, 0.82);}  // A# - Purple
    else if (pc == 11) {color = vec3(0.90, 0.45, 0.58);}  // B  - Pink
    return color;
}

// Channel colors (legacy, used when note index not available)
vec3 getChannelColor(int channel) {
    return vec3(0.5);
}

// Get color of a piano key by index
vec3 getKeyColor(int index) {
    if (isWhiteKey(index))
        return WHITE_COLOR;
    return BLACK_COLOR;
}

// Divisors shenanigans
struct Segment {
    int   A;
    float Ax;
    int   B;
    float Bx;
};

// X: (0 - 1), A: 1-oo, B: 1-oo
Segment makeSegment(float x, int a, int b, int offset) {
    Segment S;
    S.A  = offset + int(a*x);
    S.Ax = fract(a*x);
    S.B  = offset + int(b*x)*2;
    S.Bx = fract(b*x);
    return S;
}

// Count white keys from MIDI note 0 up to (not including) note n
float whiteKeysBelow(int n) {
    // Each octave has 7 white keys (C D E F G A B)
    int octaves = n / 12;
    int pc = ((n % 12) + 12) % 12;
    // White keys per pitch class: C=0,D=1,E=2,F=3,G=4,A=5,B=6
    // Cumulative whites at each pc: 0,1,1,2,2,3,3,4,4,5,5,6
    int cumWhites[12] = int[12](0,1,1,2,2,3,3,4,4,5,5,6);
    return float(octaves * 7 + cumWhites[pc]);
}

// Convert MIDI note to rollUV.x using white-key spacing
float midiToRollX(int midi, vec2 pianoDynamic, float pianoExtra) {
    float minNote = pianoDynamic.x - pianoExtra;
    float maxNote = pianoDynamic.y + pianoExtra;
    float totalWhites = whiteKeysBelow(int(maxNote) + 1) - whiteKeysBelow(int(minNote));
    float noteWhites = whiteKeysBelow(midi) - whiteKeysBelow(int(minNote));

    int pc = ((midi % 12) + 12) % 12;
    bool isWhite = (pc==0||pc==2||pc==4||pc==5||pc==7||pc==9||pc==11);
    if (isWhite) {
        noteWhites += 0.5; // center of white key
    }

    return noteWhites / totalWhites;
}

// Sample text atlas at the correct UV for a given entry
vec4 sampleTextAtlas(sampler2D atlas, vec2 atlasSize, float v0, float v1, vec2 localUV) {
    // localUV.x: 0-1 across the column width
    // localUV.y: 0-1 within the text entry height
    float atlasV = mix(v0, v1, localUV.y);
    float atlasU = localUV.x;
    return texture(atlas, vec2(atlasU, atlasV));
}

void main() {
    GetCamera(iCamera);

    if (iCamera.out_of_bounds) {
        fragColor = vec4(vec3(0.1), 1);
        return;
    }

    fragColor = vec4(vec3(0.2), 1);
    vec2 uv = iCamera.astuv;

    #if HORIZONTAL
        uv = vec2(uv.y, uv.x);
    #endif

    // No chord column — full width for roll
    float colWidth = 0.0;
    vec2 rollUV = uv;

    // Intro time offset: songTime is the effective music playback time
    float songTime = max(0.0, iTime - iIntroDuration);
    bool inIntro = (iIntroDuration > 0.0 && iTime < iIntroDuration);

    {

        // Calculate indices and coordinates using remapped UV
        float iPianoMin = (iPianoDynamic.x - iPianoExtra) - 0.1;
        float iPianoMax = (iPianoDynamic.y + iPianoExtra) + 0.1;
        float octave    = abs(mix(iPianoMin, iPianoMax, rollUV.x))/12;
        float nkeys     = abs(iPianoMax - iPianoMin);
        float whiteSize = 12.0/( 7*nkeys);
        float blackSize = 12.0/(12*nkeys);
        Segment segment;

        /* Ugly calculate segments */ {
            float divisor  = (3.0/7.0);
            bool  first    = fract(octave) < divisor;
            int   offset   = 12*int(octave) + (first?0:5);
            float segmentX = first ? (fract(octave)/divisor) : (fract(octave)-divisor)/(1.0-divisor);
            segment = makeSegment(segmentX, (first?5:7), (first?3:4), offset);

            // Make lines based on start and end of segmentX
            fragColor.rgb += 0.1*pow(abs(segmentX*2 - 1), 100);
        }

        // Get properties
        int   rollIndex   = segment.A;
        int   whiteIndex  = segment.B;
        float rollX       = segment.Ax;
        float whiteX      = segment.Bx;
        float blackHeight = iPianoHeight*(1 - iPianoBlackRatio);

        // Out of bounds
        if (uv.y < (-1) * BLEED) {}

        // Inside the piano keys
        else if (uv.y < iPianoHeight && inIntro) {
            // ===== INTRO: Static one-octave scale keyboard =====
            float introFade = smoothstep(0.0, 0.5, iTime) * smoothstep(iIntroDuration, iIntroDuration - 0.5, iTime);
            float keyY = uv.y / iPianoHeight;  // 0=bottom, 1=top

            // One octave = 7 white keys, centered horizontally
            float kbWidth = 0.55;  // keyboard width as fraction of screen
            float kbLeft = (1.0 - kbWidth) * 0.5;
            float kbRight = kbLeft + kbWidth;

            if (uv.x >= kbLeft && uv.x <= kbRight) {
                float kbX = (uv.x - kbLeft) / kbWidth;  // 0..1 across keyboard
                int whiteIdx = int(kbX * 7.0);  // 0-6
                float whiteLocalX = fract(kbX * 7.0);  // 0..1 within white key

                // White key pitch classes: C=0, D=2, E=4, F=5, G=7, A=9, B=11
                int whitePCs[7] = int[7](0, 2, 4, 5, 7, 9, 11);
                int pc = whitePCs[min(whiteIdx, 6)];

                // Check if this is a black key area (top 60% of key)
                // Black keys sit between: C#(0-1), D#(1-2), F#(3-4), G#(4-5), A#(5-6)
                bool inBlackKey = false;
                int blackPC = -1;
                if (keyY > 0.4) {  // black keys in upper portion
                    // Black key positions (between white key boundaries)
                    float bkWidth = 0.6;  // black key width relative to white key
                    float bkHalf = bkWidth * 0.5;
                    // Check right edge of current white key for black key
                    bool hasBlackRight = (whiteIdx == 0 || whiteIdx == 1 || whiteIdx == 3 || whiteIdx == 4 || whiteIdx == 5);
                    bool hasBlackLeft = (whiteIdx == 1 || whiteIdx == 2 || whiteIdx == 4 || whiteIdx == 5 || whiteIdx == 6);
                    int blackRightPCs[7] = int[7](1, 3, -1, 6, 8, 10, -1);
                    int blackLeftPCs[7] = int[7](-1, 1, 3, -1, 6, 8, 10);

                    if (hasBlackRight && whiteLocalX > (1.0 - bkHalf)) {
                        inBlackKey = true;
                        blackPC = blackRightPCs[min(whiteIdx, 6)];
                    } else if (hasBlackLeft && whiteLocalX < bkHalf) {
                        inBlackKey = true;
                        blackPC = blackLeftPCs[min(whiteIdx, 6)];
                    }
                }

                if (inBlackKey && blackPC >= 0) {
                    // Black key
                    bool inScale = ((iIntroScaleMask >> blackPC) & 1) == 1;
                    if (inScale) {
                        fragColor.rgb = getNoteColor(blackPC) * 0.7;
                    } else {
                        fragColor.rgb = vec3(0.25);
                    }
                } else {
                    // White key
                    bool inScale = ((iIntroScaleMask >> pc) & 1) == 1;
                    vec3 wkColor = inScale ? getNoteColor(pc) : vec3(0.92) * 0.3;
                    // Separation lines
                    wkColor *= smoothstep(0.0, 0.02, whiteLocalX) * smoothstep(1.0, 0.98, whiteLocalX);
                    fragColor.rgb = wkColor;
                }

                // Key label on white keys that are in scale (bottom area)
                if (!inBlackKey && keyY < 0.22) {
                    bool inScale = ((iIntroScaleMask >> pc) & 1) == 1;
                    if (inScale) {
                        // Render key label from iKeyLabelAtlas
                        int labelIdx = -1;
                             if (pc == 0) labelIdx = 0;  // C
                        else if (pc == 2) labelIdx = 1;  // D
                        else if (pc == 4) labelIdx = 2;  // E
                        else if (pc == 5) labelIdx = 3;  // F
                        else if (pc == 7) labelIdx = 4;  // G
                        else if (pc == 9) labelIdx = 5;  // A
                        else if (pc == 11) labelIdx = 6; // B

                        if (labelIdx >= 0) {
                            float labelV0 = float(labelIdx) * iKeyLabelRowH / iKeyLabelAtlasSize.y;
                            float labelV1 = float(labelIdx + 1) * iKeyLabelRowH / iKeyLabelAtlasSize.y;
                            float glV0 = 1.0 - labelV1;
                            float glV1 = 1.0 - labelV0;
                            // Fixed pixel height for label, maintain aspect ratio
                            float atlasEntryW = iKeyLabelAtlasSize.x;
                            float atlasEntryH = iKeyLabelRowH;
                            float labelPixH = 56.0;
                            float labelPixW = labelPixH * (atlasEntryW / atlasEntryH);
                            float wkPixW = (kbWidth / 7.0) * iResolution.x;
                            float keyPixH = iPianoHeight * iResolution.y;
                            float labelW = labelPixW / wkPixW;  // as fraction of key width
                            float labelH = labelPixH / keyPixH;  // as fraction of key height
                            float labelTop = 0.20;
                            float labelBot = labelTop - labelH;
                            if (keyY > labelBot && keyY < labelTop) {
                                float lx = (whiteLocalX - 0.5) / labelW + 0.5;
                                float ly = (keyY - labelBot) / labelH;
                                if (lx >= 0.0 && lx <= 1.0) {
                                    vec4 lc = sampleTextAtlas(iKeyLabelAtlas, iKeyLabelAtlasSize, glV0, glV1, vec2(lx, ly));
                                    if (lc.a > 0.1) {
                                        fragColor.rgb = mix(fragColor.rgb, vec3(1.0), lc.a * 0.9);
                                    }
                                }
                            }
                        }
                    }
                }

                fragColor.rgb *= introFade;
            } else {
                fragColor = vec4(vec3(0.12), 1.0);
            }
        }
        else if (uv.y < iPianoHeight) {
            bool white     = (isWhiteKey(rollIndex) || (uv.y < blackHeight) || (uv.y > iPianoHeight));
            int  keyIndex  = white ? whiteIndex:rollIndex;
            vec2 whiteStuv = vec2(whiteX, uv.y/iPianoHeight);
            vec2 blackStuv = vec2(rollX, lerp(blackHeight, 0, iPianoHeight, 1, uv.y));
            vec2 keyStuv   = white?whiteStuv:blackStuv;
            bool black     = !white;

            // Get note properties
            vec3 noteColor    = getNoteColor(keyIndex);
            vec3 keyColor     = getKeyColor(keyIndex);
            vec2 keyGluv      = stuv2gluv(keyStuv);
            float press       = (texelFetch(iPianoKeys, ivec2(keyIndex, 0), 0).r)/128;
            float dark        = mix(1, 0.5, press) * (black?0.3+press:0.8);
            float down        = mix(0.11, 0, press); // Key perspective

            // Check if this key is used in the song
            float used = texelFetch(iUsedKeys, ivec2(keyIndex, 0), 0).r;

            // Color the key: used keys are bold by default, lighter when pressed
            if (used > 0.5) {
                float tint = press > 0.01 ? mix(0.85, 0.4, pow(abs(press), 0.5)) : 0.85;
                fragColor.rgb = mix(keyColor, noteColor, tint);
            } else {
                // Grey out unused keys
                fragColor.rgb = black ? vec3(0.30) : vec3(0.35);
            }

            // Press animation
            if (keyStuv.y < down+iPianoHeight*0.1) {
                fragColor.rgb *= dark;
            }

            // Vintage black shading
            fragColor.rgb *= pow(1 - abs(max(0, keyGluv.y)), 0.1);

            // Concave body effect
            if (black) fragColor.rgb *= pow(1 - abs(keyGluv.x), 0.1);

            // Separation lines
            fragColor.rgb *= (0.7 - press) + (press + 0.3)*pow(1 - abs(keyGluv.x), 0.1);

            // Fade to Black
            fragColor.rgb *= pow(1 - 1*press*(uv.y/iPianoHeight), 0.3);

            // Note name label on used white keys
            if (white && used > 0.5) {
                int pc = keyIndex % 12;
                int labelIdx = -1;
                     if (pc == 0) labelIdx = 0;  // C
                else if (pc == 2) labelIdx = 1;  // D
                else if (pc == 4) labelIdx = 2;  // E
                else if (pc == 5) labelIdx = 3;  // F
                else if (pc == 7) labelIdx = 4;  // G
                else if (pc == 9) labelIdx = 5;  // A
                else if (pc == 11) labelIdx = 6; // B

                if (labelIdx >= 0) {
                    float labelV0 = float(labelIdx) * iKeyLabelRowH / iKeyLabelAtlasSize.y;
                    float labelV1 = float(labelIdx + 1) * iKeyLabelRowH / iKeyLabelAtlasSize.y;
                    float glV0 = 1.0 - labelV1;
                    float glV1 = 1.0 - labelV0;

                    // Calculate label size preserving aspect ratio
                    float atlasEntryW = iKeyLabelAtlasSize.x;
                    float atlasEntryH = iKeyLabelRowH;
                    float keyPixelW = whiteSize * iResolution.x;
                    float keyPixelH = iPianoHeight * iResolution.y;
                    // Scale label to fit key width, maintain aspect ratio
                    float labelPixH = keyPixelW * (atlasEntryH / atlasEntryW) * 0.25;
                    float labelH = labelPixH / keyPixelH;  // as fraction of key height

                    // Position: centered horizontally, upper portion of key (30% from top)
                    float labelTop = 0.35;
                    float labelBot = labelTop - labelH;

                    // Label display width as fraction of key width (same scale as height)
                    float labelW = labelPixH * (atlasEntryW / atlasEntryH) / keyPixelW;
                    float labelLeft = 0.5 - labelW * 0.5;
                    float labelRight = 0.5 + labelW * 0.5;

                    if (keyStuv.y > labelBot && keyStuv.y < labelTop &&
                        whiteStuv.x > labelLeft && whiteStuv.x < labelRight) {
                        float localX = (whiteStuv.x - labelLeft) / labelW;
                        float localY = (keyStuv.y - labelBot) / labelH;

                        vec4 lc = sampleTextAtlas(iKeyLabelAtlas, iKeyLabelAtlasSize,
                                                  glV0, glV1, vec2(localX, localY));
                        if (lc.a > 0.1) {
                            fragColor.rgb = mix(fragColor.rgb, vec3(0.0), lc.a * 0.85);
                        }
                    }
                }
            }

            // Top border
            float topBorder = iPianoHeight*(1 - TOP_BORDER);
            if (uv.y > topBorder) {
                vec2 uv = vec2(uv.x, lerp(topBorder, -1, iPianoHeight, 1, uv.y));
                fragColor.rgb = vec3(232, 7, 0)/255;
                fragColor.rgb *= 1 - 0.6*pow(length(uv.y), 1);
            }

        // Inside the 'Roll'
        } else {

          // ===== INTRO SCREEN (above piano, replaces roll during intro) =====
          if (inIntro) {
            fragColor = vec4(vec3(0.12), 1.0);

            // Render intro text: title centered, BPM and KEY below
            float introFade = smoothstep(0.0, 0.5, iTime) * smoothstep(iIntroDuration, iIntroDuration - 0.5, iTime);

            // Title — center-right, large
            {
                float v0 = 1.0 - iIntroTitleV.y;  // flip for GL
                float v1 = 1.0 - iIntroTitleV.x;
                float texH = abs(v1 - v0) * iIntroAtlasSize.y;
                float texW = iIntroAtlasSize.x;
                float displayPixH = (iVerticalMode == 1) ? 80.0 : 100.0;
                float displayPixW = displayPixH * (texW / texH);
                float displayW = displayPixW / iResolution.x;
                float displayH = displayPixH / iResolution.y;

                float centerX = 0.55;
                float centerY = 0.65;
                float localX = (uv.x - centerX) / displayW + 0.5;
                float localY = (uv.y - centerY) / displayH + 0.5;

                if (localX >= 0.0 && localX <= 1.0 && localY >= 0.0 && localY <= 1.0) {
                    vec4 tc = sampleTextAtlas(iIntroAtlas, iIntroAtlasSize, v0, v1, vec2(localX, localY));
                    if (tc.a > 0.1) {
                        fragColor.rgb = mix(fragColor.rgb, vec3(1.0), tc.a * introFade);
                    }
                }
            }

            // BPM — below title, left of center-right area
            {
                float v0 = 1.0 - iIntroBpmV.y;
                float v1 = 1.0 - iIntroBpmV.x;
                float texH = abs(v1 - v0) * iIntroAtlasSize.y;
                float texW = iIntroAtlasSize.x;
                float displayPixH = (iVerticalMode == 1) ? 180.0 : 210.0;
                float displayPixW = displayPixH * (texW / texH);
                float displayW = displayPixW / iResolution.x;
                float displayH = displayPixH / iResolution.y;

                float centerX = 0.42;
                float centerY = 0.45;
                float localX = (uv.x - centerX) / displayW + 0.5;
                float localY = (uv.y - centerY) / displayH + 0.5;

                if (localX >= 0.0 && localX <= 1.0 && localY >= 0.0 && localY <= 1.0) {
                    vec4 tc = sampleTextAtlas(iIntroAtlas, iIntroAtlasSize, v0, v1, vec2(localX, localY));
                    if (tc.a > 0.1) {
                        fragColor.rgb = mix(fragColor.rgb, tc.rgb * vec3(1.0), tc.a * introFade);
                    }
                }
            }

            // KEY — below title, right of center-right area
            {
                float v0 = 1.0 - iIntroKeyV.y;
                float v1 = 1.0 - iIntroKeyV.x;
                float texH = abs(v1 - v0) * iIntroAtlasSize.y;
                float texW = iIntroAtlasSize.x;
                float displayPixH = (iVerticalMode == 1) ? 180.0 : 210.0;
                float displayPixW = displayPixH * (texW / texH);
                float displayW = displayPixW / iResolution.x;
                float displayH = displayPixH / iResolution.y;

                float centerX = 0.68;
                float centerY = 0.45;
                float localX = (uv.x - centerX) / displayW + 0.5;
                float localY = (uv.y - centerY) / displayH + 0.5;

                if (localX >= 0.0 && localX <= 1.0 && localY >= 0.0 && localY <= 1.0) {
                    vec4 tc = sampleTextAtlas(iIntroAtlas, iIntroAtlasSize, v0, v1, vec2(localX, localY));
                    if (tc.a > 0.1) {
                        fragColor.rgb = mix(fragColor.rgb, tc.rgb * vec3(1.0), tc.a * introFade);
                    }
                }
            }

          } else {
            // ===== NORMAL ROLL =====

            // Piano roll canvas coordinate (-1 to 1)
            vec2 roll = vec2(rollUV.x, lerp(iPianoHeight, 0, 1, 1, uv.y));
            float seconds = iTime+iPianoRollTime*roll.y;

            // Find the current tempo on iPianoTempo texture, pairs or (when, tempo)
            float beat = 120;
            for (int i=0; i<100; i++) {
                vec4 tempo = texelFetch(iPianoTempo, ivec2(i, 0), 0);
                if (tempo.y < 1) break;
                beat = 60.0/tempo.y;
                if (seconds < tempo.x) {
                    break;
                }
            }

            /* Draw the beat lines */ {
                float full = fract(seconds/beat/4);
                float beat = fract(seconds/beat);

                fragColor.rgb += 0.1*pow(max(2*full-1, 1-2*full), 500);
                fragColor.rgb += 0.3*pow(max(2*beat-1, 1-2*beat), 80)*(abs(agluv.x)>0.97?1:0);
            }

            // Draw the white key then black key
            for (int layer=0; layer<2; layer++) {

                // Skip drawing a duplicate black on top of white
                if ((layer == 1) && isWhiteKey(rollIndex)) {continue;}

                // Get the index we are matching depending on the pass
                int thisIndex = int(mix(whiteIndex, rollIndex, float(layer)));

                // Search for playing notes: (Start, End, Channel, Velocity)
                for (int i=0; i<iPianoLimit; i++) {
                    vec4 note = texelFetch(iPianoRoll, ivec2(i, thisIndex), 0);
                    if (note.w < 1) break;

                    // Local coordinate for the note
                    vec2 nagluv = vec2(
                        mix(whiteX, rollX, float(layer))*2 - 1,
                        lerp(note.x, -1, note.y, 1, seconds)
                    );

                    // Check if we are inside the note
                    if (abs(nagluv.y) < 1 && abs(nagluv.x) < 1) {
                        float velocity  = int(note.w);
                        float duration  = abs(note.y - note.x);
                        float thisSizeX = mix(whiteSize, blackSize, float(layer));
                        float thisSizeY = (duration/iPianoRollTime)*(1-iPianoHeight)/iAspectRatio;
                        bool  thisBlack = isBlackKey(thisIndex);
                        vec3  thisColor = getNoteColor(thisIndex);

                        // "Real" scene distances
                        vec2 real = vec2(
                            lerp(0, (1-thisSizeX/2), 1, 1, abs(nagluv.x)),
                            lerp(0, (1-thisSizeY/2), 1, 1, abs(nagluv.y))
                        );

                        // Rounded rectangle SDF
                        float cornerR = 0.004;
                        vec2 d = real - vec2(1.0 - cornerR);
                        float sdf = length(max(d, 0.0)) - cornerR;
                        float border = 1.0 - smoothstep(-0.001, 0.001, sdf);

                        vec3 color = thisColor * (thisBlack ? 0.55 : 1.0);
                        fragColor.rgb = mix(fragColor.rgb, color, border);
                    }
                }
            }

            // ===== CHORD LABELS (overlay on roll, top-left aligned) =====
            if (iChordCount > 0) {
                float rollPixH = (1.0 - iPianoHeight) * iResolution.y;

                for (int i = 0; i < iChordCount; i++) {
                    vec4 chordData = texelFetch(iChordTiming, ivec2(0, i), 0);
                    float chordTime = chordData.x;
                    float v0 = chordData.z;
                    float v1 = chordData.w;

                    // Fixed pixel height, 1.5x bigger
                    float fixedPixH = (iVerticalMode == 1) ? 108.0 : 63.0;
                    float texH = abs(v1 - v0) * iChordAtlasSize.y;
                    float texW = iChordAtlasSize.x;
                    float displayPixW = fixedPixH * (texW / texH);
                    float displayW = displayPixW / iResolution.x;
                    float displayHFrac = fixedPixH / iResolution.y;
                    float textHeightSec = displayHFrac * iPianoRollTime / (1.0 - iPianoHeight);

                    if (seconds >= chordTime && seconds < chordTime + textHeightSec) {
                        float localY = (seconds - chordTime) / textHeightSec;
                        // Align left: text starts at left edge with small padding
                        float padX = 0.01;
                        float localX = (uv.x - padX) / displayW;
                        if (localX >= 0.0 && localX <= 1.0) {
                            vec4 texColor = sampleTextAtlas(iChordAtlas, iChordAtlasSize, v0, v1, vec2(localX, localY));
                            if (texColor.a > 0.1) {
                                fragColor.rgb = mix(fragColor.rgb, vec3(1.0, 0.9, 0.3), texColor.a);
                            }
                        }
                    }
                }
            }

            // ===== LYRICS ON NOTES (mode 0) =====
            if (iLyricMode == 0 && iLyricCount > 0) {
                float rollPixelH = (1.0 - iPianoHeight) * iResolution.y;
                float rollPixelW = (1.0 - colWidth) * iResolution.x;
                float secPerPixel = iPianoRollTime / rollPixelH;

                for (int i = 0; i < iLyricCount; i++) {
                    vec4 lyricData = texelFetch(iLyricTiming, ivec2(0, i), 0);
                    float lyricTime = lyricData.x;
                    float noteMidi = lyricData.y;
                    float v0 = lyricData.z;
                    float v1 = lyricData.w;

                    // Text natural size
                    float texH = abs(v1 - v0) * iLyricAtlasSize.y;
                    float texW = iLyricAtlasSize.x;
                    // Display width: scale to a fixed pixel height, maintain aspect ratio
                    float displayPixH = 56.0;  // fixed pixel height for text
                    float displayPixW = displayPixH * (texW / texH);
                    float displayW = displayPixW / rollPixelW;
                    float displayH = displayPixH / rollPixelH;
                    float textHeightSec = displayH * iPianoRollTime;

                    // Note center X in roll UV space - match piano key layout
                    float noteCenterX = midiToRollX(int(noteMidi), iPianoDynamic, iPianoExtra);
                    // Note edge: white key half-width in rollUV
                    float iPianoMin = iPianoDynamic.x - iPianoExtra;
                    float iPianoMax = iPianoDynamic.y + iPianoExtra;
                    float nkeys = iPianoMax - iPianoMin;
                    float halfKeyW = 6.0 / (7.0 * nkeys);

                    if (seconds >= lyricTime && seconds < lyricTime + textHeightSec) {
                        float localY = (seconds - lyricTime) / textHeightSec;
                        float localX;
                        if (noteCenterX < 0.5) {
                            // Left half: text starts at right edge of note
                            float textStartX = noteCenterX + halfKeyW;
                            localX = (rollUV.x - textStartX) / displayW;
                        } else {
                            // Right half: text ends at left edge of note
                            float textEndX = noteCenterX - halfKeyW;
                            localX = (rollUV.x - textEndX) / displayW + 1.0;
                        }
                        if (localX >= -0.05 && localX <= 1.05) {
                            // Black outline: uniform in screen space
                            float strokePx = 1.0;
                            float stepX = strokePx / displayPixW;
                            float stepY = strokePx / displayPixH;
                            float outline = 0.0;
                            for (int ox = -2; ox <= 2; ox++) {
                                for (int oy = -2; oy <= 2; oy++) {
                                    if (ox == 0 && oy == 0) continue;
                                    vec2 off = vec2(float(ox) * stepX, float(oy) * stepY);
                                    vec4 s = sampleTextAtlas(iLyricAtlas, iLyricAtlasSize, v0, v1, vec2(localX, localY) + off);
                                    outline = max(outline, s.a);
                                }
                            }
                            if (outline > 0.1) {
                                fragColor.rgb = mix(fragColor.rgb, vec3(1.0), outline * 0.9);
                            }
                            // Black text on top
                            vec4 texColor = sampleTextAtlas(iLyricAtlas, iLyricAtlasSize, v0, v1, vec2(localX, localY));
                            if (texColor.a > 0.1) {
                                fragColor.rgb = mix(fragColor.rgb, vec3(0.0), texColor.a * 0.95);
                            }
                        }
                    }
                }
            }

            // ===== KARAOKE MODE (mode 1) =====
            if (iLyricMode == 1 && iLyricCount > 0) {
                // Two fixed slots. Lines alternate: even lines → slot 0, odd → slot 1.
                // Each line stays in its slot until it ends, then the next line fills the free slot.
                // slot0Line and slot1Line: which line index is in each slot
                int slot0Line = -1;
                int slot1Line = -1;

                // Find which lines should be displayed
                for (int i = 0; i < iLyricCount; i++) {
                    vec4 lineData = texelFetch(iLyricTiming, ivec2(0, i), 0);
                    float startT = lineData.x;
                    float endT = lineData.y;
                    // Line is visible if started and not yet ended
                    if (startT <= iTime && iTime < endT) {
                        // Assign to slot based on line parity (even→0, odd→1)
                        if (i % 2 == 0) slot0Line = i;
                        else slot1Line = i;
                    }
                    // Also pre-show next line if current slot is empty
                    if (startT > iTime && startT - iTime < 2.0) {
                        if (i % 2 == 0 && slot0Line == -1) slot0Line = i;
                        else if (i % 2 == 1 && slot1Line == -1) slot1Line = i;
                        break;
                    }
                }

                // Render 2 slots at center of roll
                float lineHeight = 0.05;
                float topY = (iVerticalMode == 1) ? 0.65 : 0.92;
                float gap = (iVerticalMode == 1) ? 1.0 : 2.5;
                float slot0Y = topY;                         // top slot
                float slot1Y = topY - lineHeight * gap;      // bottom slot

                for (int pass = 0; pass < 2; pass++) {
                    int lineIdx = (pass == 0) ? slot0Line : slot1Line;
                    if (lineIdx < 0) continue;
                    float targetY = (pass == 0) ? slot0Y : slot1Y;

                    // Is this the actively singing line?
                    vec4 ld = texelFetch(iLyricTiming, ivec2(0, lineIdx), 0);
                    bool isActive = (ld.x <= iTime);

                    float v0 = ld.z;
                    float v1 = ld.w;

                    // Display size: scale to fit roll width
                    float texH = abs(v1 - v0) * iLyricAtlasSize.y;
                    float texW = iLyricAtlasSize.x;
                    float displayW = (iVerticalMode == 1) ? 1.2 : 0.8;
                    float displayH = displayW * (texH / texW) * iAspectRatio;

                    float centerX = 0.5;
                    float localX = (rollUV.x - centerX) / displayW + 0.5;
                    float localY = (uv.y - targetY) / displayH + 0.5;

                    if (localX >= 0.0 && localX <= 1.0 && localY >= 0.0 && localY <= 1.0) {
                        vec4 texColor = sampleTextAtlas(iLyricAtlas, iLyricAtlasSize, v0, v1, vec2(localX, localY));
                        if (texColor.a > 0.1) {
                            // Dim for upcoming, brighter for active
                            vec3 textColor = isActive ? vec3(0.6) : vec3(0.35);

                            // Highlight sung syllables on active line
                            if (isActive) {
                                for (int s = 0; s < iSyllableCount; s++) {
                                    vec4 sylData = texelFetch(iSyllableTiming, ivec2(0, s), 0);
                                    if (int(sylData.y) != lineIdx) continue;
                                    if (sylData.x <= iTime && localX >= sylData.z && localX <= sylData.w) {
                                        textColor = vec3(1.0, 1.0, 1.0);
                                    }
                                }
                            }

                            fragColor.rgb = mix(fragColor.rgb, textColor, texColor.a * 0.95);
                        }
                    }
                }
            }
          } // end else (normal roll vs intro)
        }
    }
    // // Post Effects

    // Vignette
    #if VIGNETTE
        vec2 vig = astuv * (1 - astuv.yx);
        fragColor.rgb *= pow(vig.x*vig.y * 10, 0.05);
        fragColor.a = 1;
    #endif

    // Progress bar
    if (
        ((1 - PBAR_SIZE) < uv.y) && (uv.y < 1 + BLEED) &&
        ((-1)*BLEED < uv.x) && (uv.x < iTau) && (uv.x < 1 + BLEED)
    ) {
        fragColor.rgb *= 0.8 - 0.2 * smoothstep(0, 1, uv.x);
    }

    // Fade in/out
    float fade = 2.0;
    if (iRendering) {
        fragColor.rgb *= mix(0, 1, smoothstep(0, fade, iTime));
        fragColor.rgb *= mix(1, 0, smoothstep(iDuration - fade, iDuration, iTime));
    }

    return;
}
