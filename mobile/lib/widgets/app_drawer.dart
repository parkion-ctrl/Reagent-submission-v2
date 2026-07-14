import 'package:flutter/material.dart';

import '../api_client.dart';
import '../screens/qr_dispense_screen.dart';
import '../screens/settings_screen.dart';

enum AppSection { inventory, qrDispense, settings }

class AppDrawer extends StatelessWidget {
  final ApiClient apiClient;
  final Map<String, dynamic> user;
  final AppSection current;

  const AppDrawer({super.key, required this.apiClient, required this.user, required this.current});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final username = user['username'] as String? ?? '-';
    final department = user['department'] as String? ?? '-';
    return Drawer(
      child: ListView(
        padding: EdgeInsets.zero,
        children: [
          DrawerHeader(
            decoration: BoxDecoration(color: colorScheme.primary),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Text(
                  '아주대 시약 관리 시스템',
                  style: TextStyle(color: colorScheme.onPrimary, fontSize: 20, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 14),
                Text('접속 중인 ID : $username', style: TextStyle(color: colorScheme.onPrimary, fontSize: 14)),
                const SizedBox(height: 2),
                Text('접속 중인 부서 : $department', style: TextStyle(color: colorScheme.onPrimary, fontSize: 14)),
              ],
            ),
          ),
          ListTile(
            leading: const Icon(Icons.inventory_2_outlined),
            title: const Text('재고 조회'),
            selected: current == AppSection.inventory,
            onTap: () {
              Navigator.of(context).pop();
              if (current != AppSection.inventory) {
                Navigator.of(context).popUntil((route) => route.isFirst);
              }
            },
          ),
          ListTile(
            leading: const Icon(Icons.qr_code_scanner_outlined),
            title: const Text('QR 출고 (테스트)'),
            selected: current == AppSection.qrDispense,
            onTap: () {
              Navigator.of(context).pop();
              if (current != AppSection.qrDispense) {
                Navigator.of(
                  context,
                ).push(MaterialPageRoute(builder: (_) => QrDispenseScreen(apiClient: apiClient)));
              }
            },
          ),
          ListTile(
            leading: const Icon(Icons.settings_outlined),
            title: const Text('설정'),
            selected: current == AppSection.settings,
            onTap: () {
              Navigator.of(context).pop();
              if (current != AppSection.settings) {
                Navigator.of(
                  context,
                ).push(MaterialPageRoute(builder: (_) => SettingsScreen(apiClient: apiClient, user: user)));
              }
            },
          ),
        ],
      ),
    );
  }
}
