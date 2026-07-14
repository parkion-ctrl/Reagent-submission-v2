import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:reagent_mobile/api_client.dart';
import 'package:reagent_mobile/screens/login_screen.dart';

void main() {
  testWidgets('Login screen shows username/password fields', (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(home: LoginScreen(apiClient: ApiClient())),
    );

    expect(find.text('아이디'), findsOneWidget);
    expect(find.text('비밀번호'), findsOneWidget);
    expect(find.text('로그인'), findsOneWidget);
  });
}
