import React, { useMemo } from 'react';
import { View, Text, StyleSheet, useWindowDimensions } from 'react-native';
import { BOARD_COLORS, ALL_COLOR_CODES } from '@fiestaboard/shared';
import { DEVICE_DIMENSIONS, BOARD_CHARS, type DeviceType } from '@fiestaboard/shared';

type Token = { type: 'char'; value: string } | { type: 'color'; code: string };

function parseLine(line: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  while (i < line.length) {
    if (line[i] === '{') {
      const closingBrace = line.indexOf('}', i);
      if (closingBrace !== -1) {
        const content = line.substring(i + 1, closingBrace);
        if (content.startsWith('/')) {
          i = closingBrace + 1;
          continue;
        }
        if (/^\d+$/.test(content) && parseInt(content) >= 63 && parseInt(content) <= 71) {
          tokens.push({ type: 'color', code: content });
          i = closingBrace + 1;
          continue;
        }
        // Named colors
        const lower = content.toLowerCase();
        if (ALL_COLOR_CODES[lower]) {
          tokens.push({ type: 'color', code: lower });
          i = closingBrace + 1;
          continue;
        }
      }
    }
    tokens.push({ type: 'char', value: line[i].toUpperCase() });
    i++;
  }
  return tokens;
}

function resolveColorCode(code: string, isWhiteBoard: boolean): string {
  if (isWhiteBoard) {
    if (code === '69' || code === 'white') return BOARD_COLORS.black;
    if (code === '70' || code === 'black') return BOARD_COLORS.white;
  }
  return ALL_COLOR_CODES[code] || BOARD_COLORS.black;
}

function getCharIndex(char: string): number {
  return BOARD_CHARS.indexOf(char);
}

interface BoardPreviewProps {
  content: string;
  deviceType?: DeviceType;
  boardColor?: 'black' | 'white';
  compact?: boolean;
}

export function BoardPreview({ content, deviceType = 'flagship', boardColor = 'black', compact = false }: BoardPreviewProps) {
  const { width: screenWidth } = useWindowDimensions();
  const dims = DEVICE_DIMENSIONS[deviceType] || DEVICE_DIMENSIONS.flagship;
  const isWhiteBoard = boardColor === 'white';

  const maxWidth = compact ? screenWidth * 0.42 : screenWidth - 32;
  const cellSize = Math.floor(maxWidth / dims.cols);
  const gap = compact ? 1 : 2;
  const boardWidth = cellSize * dims.cols + gap * (dims.cols - 1);
  const boardPadding = compact ? 4 : 8;

  const lines = useMemo(() => {
    const raw = content.split('\n');
    const result: Token[][] = [];
    for (let i = 0; i < dims.rows; i++) {
      const line = raw[i] || '';
      const tokens = parseLine(line);
      // Pad to cols
      while (tokens.length < dims.cols) {
        tokens.push({ type: 'char', value: ' ' });
      }
      result.push(tokens.slice(0, dims.cols));
    }
    return result;
  }, [content, dims.rows, dims.cols]);

  const bgColor = isWhiteBoard ? '#e8e8e8' : '#1a1a1a';
  const charColor = isWhiteBoard ? '#1a1a1a' : '#e8e0d0';
  const cellBg = isWhiteBoard ? '#f5f5f5' : '#111111';

  return (
    <View style={[styles.board, { backgroundColor: bgColor, padding: boardPadding, borderRadius: compact ? 6 : 10 }]} testID="board-preview">
      {lines.map((row, rowIdx) => (
        <View key={rowIdx} style={[styles.row, { gap }]}>
          {row.map((token, colIdx) => {
            if (token.type === 'color') {
              const color = resolveColorCode(token.code, isWhiteBoard);
              return (
                <View
                  key={colIdx}
                  style={[styles.cell, { width: cellSize, height: cellSize, backgroundColor: color, borderRadius: compact ? 1 : 2 }]}
                />
              );
            }
            return (
              <View
                key={colIdx}
                style={[styles.cell, { width: cellSize, height: cellSize, backgroundColor: cellBg, borderRadius: compact ? 1 : 2 }]}
              >
                <Text
                  style={[
                    styles.charText,
                    {
                      color: charColor,
                      fontSize: compact ? cellSize * 0.55 : cellSize * 0.6,
                    },
                  ]}
                  numberOfLines={1}
                >
                  {token.value === ' ' ? '' : token.value}
                </Text>
              </View>
            );
          })}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  board: {
    alignSelf: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 4,
    elevation: 4,
  },
  row: {
    flexDirection: 'row',
    marginBottom: 2,
  },
  cell: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  charText: {
    fontWeight: '700',
    fontFamily: 'Courier',
    textAlign: 'center',
  },
});
