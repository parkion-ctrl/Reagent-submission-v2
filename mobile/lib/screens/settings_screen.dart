import 'package:flutter/material.dart';

import '../api_client.dart';
import '../config.dart';
import '../theme_controller.dart';
import '../widgets/app_drawer.dart';
import '../widgets/logout_button.dart';

class SettingsScreen extends StatelessWidget {
  final ApiClient apiClient;
  final Map<String, dynamic> user;
  const SettingsScreen({super.key, required this.apiClient, required this.user});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('설정'),
        centerTitle: true,
        actions: [LogoutButton(apiClient: apiClient)],
      ),
      drawer: AppDrawer(apiClient: apiClient, user: user, current: AppSection.settings),
      body: ListView(
        children: [
          const _SectionHeader('계정 정보'),
          ListTile(
            leading: const Icon(Icons.person_outline),
            title: const Text('이름'),
            subtitle: Text(user['name'] as String? ?? '-'),
          ),
          ListTile(
            leading: const Icon(Icons.badge_outlined),
            title: const Text('아이디'),
            subtitle: Text(user['username'] as String? ?? '-'),
          ),
          ListTile(
            leading: const Icon(Icons.apartment_outlined),
            title: const Text('부서'),
            subtitle: Text(user['department'] as String? ?? '-'),
          ),
          ListTile(
            leading: const Icon(Icons.category_outlined),
            title: const Text('파트'),
            subtitle: Text(user['part'] as String? ?? '-'),
          ),
          const Divider(),
          const _SectionHeader('화면 설정'),
          ValueListenableBuilder<ThemeMode>(
            valueListenable: themeController,
            builder: (context, mode, _) {
              return RadioGroup<ThemeMode>(
                groupValue: mode,
                onChanged: (m) => themeController.setThemeMode(m!),
                child: const Column(
                  children: [
                    RadioListTile<ThemeMode>(title: Text('시스템 기본값'), value: ThemeMode.system),
                    RadioListTile<ThemeMode>(title: Text('라이트 모드'), value: ThemeMode.light),
                    RadioListTile<ThemeMode>(title: Text('다크 모드'), value: ThemeMode.dark),
                  ],
                ),
              );
            },
          ),
          const Divider(),
          const _SectionHeader('앱 정보'),
          const ListTile(
            leading: Icon(Icons.dns_outlined),
            title: Text('서버 주소'),
            subtitle: Text(apiBaseUrl),
          ),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  const _SectionHeader(this.title);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 20, 16, 4),
      child: Text(
        title,
        style: TextStyle(fontWeight: FontWeight.w700, color: Theme.of(context).colorScheme.primary),
      ),
    );
  }
}
