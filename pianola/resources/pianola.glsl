/* Copyright (c) 2024-2025, CC BY-SA 4.0, Tremeschin */

#define WHITE_COLOR vec3(0.9)
#define BLACK_COLOR vec3(0.2)
#define PBAR_SIZE 0.015
#define TOP_BORDER 0.03
#define HORIZONTAL 0
#define VIGNETTE 0
#define BLEED 0.02
#define COLUMN_WIDTH 0.06

// Note-name colors: C=Red, D=Orange, E=Yellow, F=Green, G=Blue, A=Purple, B=Pink
vec3 getNoteColor(int noteIndex) {
    int pc = noteIndex % 12; // pitch class: 0=C, 1=C#, 2=D, ...
    vec3 color = vec3(0.5);
         if (pc == 0)  {color = vec3(0.93, 0.26, 0.21);}  // C  - Red
    else if (pc == 1)  {color = vec3(0.93, 0.26, 0.21);}  // C# - Red
    else if (pc == 2)  {color = vec3(0.98, 0.60, 0.20);}  // D  - Orange
    else if (pc == 3)  {color = vec3(0.98, 0.60, 0.20);}  // D# - Orange
    else if (pc == 4)  {color = vec3(0.98, 0.85, 0.20);}  // E  - Yellow
    else if (pc == 5)  {color = vec3(0.42, 0.78, 0.35);}  // F  - Green
    else if (pc == 6)  {color = vec3(0.42, 0.78, 0.35);}  // F# - Green
    else if (pc == 7)  {color = vec3(0.35, 0.56, 0.93);}  // G  - Blue
    else if (pc == 8)  {color = vec3(0.35, 0.56, 0.93);}  // G# - Blue
    else if (pc == 9)  {color = vec3(0.62, 0.40, 0.85);}  // A  - Purple
    else if (pc == 10) {color = vec3(0.62, 0.40, 0.85);}  // A# - Purple
    else if (pc == 11) {color = vec3(0.91, 0.40, 0.62);}  // B  - Pink
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

    // Determine which region we're in
    bool hasChordCol = (iChordCount > 0);
    float colWidth = hasChordCol ? COLUMN_WIDTH : 0.0;
    bool inChordCol = hasChordCol && (uv.x < colWidth);
    bool inRoll = !inChordCol;

    // Remap UV for piano roll to fill the region after chord column
    vec2 rollUV = uv;
    if (hasChordCol) {
        rollUV.x = (uv.x - colWidth) / (1.0 - colWidth);
    }

    // ===================== CHORD COLUMN (left, above piano height) =====================
    if (inChordCol && uv.y >= iPianoHeight) {
        fragColor = vec4(vec3(0.12), 1);

        vec2 roll = vec2(uv.x, lerp(iPianoHeight, 0, 1, 1, uv.y));
        float seconds = iTime + iPianoRollTime * roll.y;

        float colPixelW = colWidth * iResolution.x;
        float rollPixelH = (1.0 - iPianoHeight) * iResolution.y;
        float secPerPixel = iPianoRollTime / rollPixelH;

        for (int i = 0; i < iChordCount; i++) {
            vec4 chordData = texelFetch(iChordTiming, ivec2(0, i), 0);
            float chordTime = chordData.x;
            float v0 = chordData.z;
            float v1 = chordData.w;

            float texH = abs(v1 - v0) * iChordAtlasSize.y;
            float texW = iChordAtlasSize.x;
            float displayH = texH * (colPixelW / texW);
            float textHeightSec = displayH * secPerPixel;

            if (seconds >= chordTime && seconds < chordTime + textHeightSec) {
                float localY = (seconds - chordTime) / textHeightSec;
                float localX = uv.x / colWidth;
                vec4 texColor = sampleTextAtlas(iChordAtlas, iChordAtlasSize, v0, v1, vec2(localX, localY));
                if (texColor.a > 0.1) {
                    fragColor.rgb = mix(fragColor.rgb, vec3(1.0, 0.9, 0.3), texColor.a);
                }
            }
        }

        // Separator line
        if (abs(uv.x - colWidth) < 0.001) {
            fragColor.rgb = vec3(0.3);
        }

    } else if (inChordCol) {
        // Chord column below piano height
        fragColor = vec4(vec3(0.12), 1);

    // ===================== PIANO KEYS + ROLL (center region) =====================
    } else if (inRoll) {

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

            // Color the key: blend to note color when pressed
            fragColor.rgb = mix(keyColor, noteColor, pow(abs(press), 0.5));

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

            // Top border
            float topBorder = iPianoHeight*(1 - TOP_BORDER);
            if (uv.y > topBorder) {
                vec2 uv = vec2(uv.x, lerp(topBorder, -1, iPianoHeight, 1, uv.y));
                fragColor.rgb = vec3(232, 7, 0)/255;
                fragColor.rgb *= 1 - 0.6*pow(length(uv.y), 1);
            }

        // Inside the 'Roll'
        } else {

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

                        // "Real" scene distances. This wasn't fun to code.
                        vec2 real = vec2(
                            lerp(0, (1-thisSizeX/2), 1, 1, abs(nagluv.x)),
                            lerp(0, (1-thisSizeY/2), 1, 1, abs(nagluv.y))
                        );

                        // Minimum and maximum distances to the borders
                        vec2 dist = vec2(1 - max(real.x, real.y), 1 - min(real.x, real.y));
                        vec3 color = thisColor;

                        // Round shadows "as borders"
                        float border_size = 0.002;
                        float border = (smoothstep(1, 1-border_size, real.x) * smoothstep(1, 1-border_size, real.y));
                        color *= border * (thisBlack?0.55:1.0);
                        fragColor.rgb = mix(fragColor.rgb, color, border);
                        color *= (dist.x<border*2)?0.5:1;
                        fragColor.rgb = mix(
                            fragColor.rgb,
                            fragColor.rgb*mix(0.1, 1, border),
                            mix(0, 1, border)
                        );
                    }
                }
            }

            // ===== LYRICS ON NOTES (mode 0) =====
            if (iLyricMode == 0 && iLyricCount > 0) {
                float rollPixelH = (1.0 - iPianoHeight) * iResolution.y;
                float secPerPixel = iPianoRollTime / rollPixelH;
                float rollW = (1.0 - colWidth) * iResolution.x;

                for (int i = 0; i < iLyricCount; i++) {
                    vec4 lyricData = texelFetch(iLyricTiming, ivec2(0, i), 0);
                    float lyricTime = lyricData.x;
                    float noteMidi = lyricData.y;
                    float v0 = lyricData.z;
                    float v1 = lyricData.w;

                    // Text display size
                    float texH = abs(v1 - v0) * iLyricAtlasSize.y;
                    float texW = iLyricAtlasSize.x;
                    // Fixed display width in screen fraction
                    float displayWidthFrac = 0.08;
                    float displayHeightFrac = displayWidthFrac * (texH / texW) * iAspectRatio;
                    float textHeightSec = displayHeightFrac * iPianoRollTime / (1.0 - iPianoHeight);

                    // Position: center on the note's key X position
                    float noteX = (noteMidi - iPianoDynamic.x + iPianoExtra) /
                                  (iPianoDynamic.y - iPianoDynamic.x + 2.0 * iPianoExtra);

                    if (seconds >= lyricTime && seconds < lyricTime + textHeightSec) {
                        float localY = (seconds - lyricTime) / textHeightSec;
                        float localX = (rollUV.x - noteX) / displayWidthFrac + 0.5;
                        if (localX >= 0.0 && localX <= 1.0) {
                            vec4 texColor = sampleTextAtlas(iLyricAtlas, iLyricAtlasSize, v0, v1, vec2(localX, localY));
                            if (texColor.a > 0.1) {
                                fragColor.rgb = mix(fragColor.rgb, vec3(1.0, 1.0, 1.0), texColor.a * 0.9);
                            }
                        }
                    }
                }
            }

            // ===== KARAOKE MODE (mode 1) =====
            if (iLyricMode == 1 && iLyricCount > 0) {
                // Find current line: last line whose start_time <= iTime
                int currentLine = -1;
                int nextLine = -1;
                for (int i = 0; i < iLyricCount; i++) {
                    vec4 lineData = texelFetch(iLyricTiming, ivec2(0, i), 0);
                    if (lineData.x <= iTime) {
                        currentLine = i;
                    } else {
                        if (currentLine == -1) currentLine = i;
                        break;
                    }
                }
                nextLine = currentLine + 1;
                if (nextLine >= iLyricCount) nextLine = -1;

                // Render 2 lines at center of roll
                float lineHeight = 0.05;
                float centerY = 0.5 * (iPianoHeight + 1.0);
                float line1Y = centerY + lineHeight * 0.7;
                float line2Y = centerY - lineHeight * 0.7;

                for (int pass = 0; pass < 2; pass++) {
                    int lineIdx = (pass == 0) ? currentLine : nextLine;
                    if (lineIdx < 0) continue;
                    float targetY = (pass == 0) ? line1Y : line2Y;

                    vec4 lineData = texelFetch(iLyricTiming, ivec2(0, lineIdx), 0);
                    float v0 = lineData.z;
                    float v1 = lineData.w;

                    // Display size: scale to fit roll width
                    float texH = abs(v1 - v0) * iLyricAtlasSize.y;
                    float texW = iLyricAtlasSize.x;
                    float displayW = 0.8;
                    float displayH = displayW * (texH / texW) * iAspectRatio;

                    float centerX = 0.5;
                    float localX = (rollUV.x - centerX) / displayW + 0.5;
                    float localY = (uv.y - targetY) / displayH + 0.5;

                    if (localX >= 0.0 && localX <= 1.0 && localY >= 0.0 && localY <= 1.0) {
                        vec4 texColor = sampleTextAtlas(iLyricAtlas, iLyricAtlasSize, v0, v1, vec2(localX, localY));
                        if (texColor.a > 0.1) {
                            // Base color: dim white for upcoming, brighter for current
                            vec3 textColor = (pass == 0) ? vec3(0.6) : vec3(0.35);

                            // Highlight sung syllables on current line
                            if (pass == 0) {
                                // localX is 0..1 in display space, same as atlas U
                                for (int s = 0; s < iSyllableCount; s++) {
                                    vec4 sylData = texelFetch(iSyllableTiming, ivec2(0, s), 0);
                                    if (int(sylData.y) != lineIdx) continue;
                                    if (sylData.x <= iTime && localX >= sylData.z && localX <= sylData.w) {
                                        textColor = vec3(1.0, 1.0, 0.3);
                                    }
                                }
                            }

                            fragColor.rgb = mix(fragColor.rgb, textColor, texColor.a * 0.95);
                        }
                    }
                }
            }
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
