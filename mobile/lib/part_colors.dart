import 'package:flutter/material.dart';

// CP-Light1 / CP-Dark1 팔레트. ZZ는 각 모드의 무채색(회색) 팔레트를 사용.
const Map<String, Color> partColorsLight = {
  'HE': Color(0xFFFBB4B4),
  'BB': Color(0xFFFFDBB1),
  'IM': Color(0xFFFFFCC9),
  'ML': Color(0xFFD9FFC2),
  'CO': Color(0xFF89DEFF),
  'TA': Color(0xFF96B5FE),
  'PB': Color(0xFFD8ADF0),
  'ZZ': Color(0xFFCDCDCD),
};

const Map<String, Color> partColorsDark = {
  'HE': Color(0xFFF9514B),
  'BB': Color(0xFFE9803A),
  'IM': Color(0xFFFACB30),
  'ML': Color(0xFF349326),
  'CO': Color(0xFF22B3B3),
  'TA': Color(0xFF3556B8),
  'PB': Color(0xFF7C4B9F),
  'ZZ': Color(0xFF575757),
};

const _fallbackLight = Color(0xFFCDCDCD);
const _fallbackDark = Color(0xFF575757);

Color partColorFor(String? code, Brightness brightness) {
  if (brightness == Brightness.dark) {
    return partColorsDark[code] ?? _fallbackDark;
  }
  return partColorsLight[code] ?? _fallbackLight;
}

/// 배경색의 밝기에 맞춰 읽기 좋은 텍스트 색을 골라줍니다.
/// (예: 다크 모드의 노란색 IM 배경 위에 흰 글자가 묻히는 문제 방지)
Color readableTextOn(Color background) {
  return background.computeLuminance() > 0.45 ? const Color(0xFF1B1F1D) : Colors.white;
}
