import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class ThemeController extends ValueNotifier<ThemeMode> {
  ThemeController() : super(ThemeMode.system);

  final _storage = const FlutterSecureStorage();
  static const _key = 'theme_mode';

  Future<void> load() async {
    final saved = await _storage.read(key: _key);
    value = ThemeMode.values.firstWhere(
      (m) => m.name == saved,
      orElse: () => ThemeMode.system,
    );
  }

  Future<void> setThemeMode(ThemeMode mode) async {
    value = mode;
    await _storage.write(key: _key, value: mode.name);
  }
}

final themeController = ThemeController();
