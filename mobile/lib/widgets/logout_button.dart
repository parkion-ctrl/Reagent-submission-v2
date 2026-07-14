import 'package:flutter/material.dart';

import '../api_client.dart';
import '../screens/login_screen.dart';

class LogoutButton extends StatelessWidget {
  final ApiClient apiClient;
  const LogoutButton({super.key, required this.apiClient});

  Future<void> _confirmLogout(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('로그아웃'),
        content: const Text('로그아웃 하시겠습니까?'),
        actions: [
          FilledButton(onPressed: () => Navigator.of(ctx).pop(true), child: const Text('예')),
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('아니오')),
        ],
      ),
    );
    if (confirmed != true) return;
    await apiClient.logout();
    if (!context.mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => LoginScreen(apiClient: apiClient)),
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    return IconButton(onPressed: () => _confirmLogout(context), icon: const Icon(Icons.logout));
  }
}
