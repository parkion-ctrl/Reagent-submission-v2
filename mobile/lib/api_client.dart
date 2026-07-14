import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

import 'config.dart';

class ApiException implements Exception {
  final String message;
  ApiException(this.message);
  @override
  String toString() => message;
}

class ApiClient {
  final _storage = const FlutterSecureStorage();
  String? _accessToken;
  String? _refreshToken;

  Future<void> loadTokens() async {
    _accessToken = await _storage.read(key: 'access_token');
    _refreshToken = await _storage.read(key: 'refresh_token');
  }

  bool get isLoggedIn => _accessToken != null;

  Map<String, dynamic> _decode(http.Response res) {
    return jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> login(String username, String password) async {
    final res = await http.post(
      Uri.parse('$apiBaseUrl/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'username': username, 'password': password}),
    );
    final data = _decode(res);
    if (res.statusCode != 200) {
      throw ApiException(data['detail'] as String? ?? '로그인에 실패했습니다.');
    }
    _accessToken = data['access'] as String;
    _refreshToken = data['refresh'] as String;
    await _storage.write(key: 'access_token', value: _accessToken);
    await _storage.write(key: 'refresh_token', value: _refreshToken);
    return data['user'] as Map<String, dynamic>;
  }

  Future<void> logout() async {
    _accessToken = null;
    _refreshToken = null;
    await _storage.deleteAll();
  }

  Future<bool> _refreshAccessToken() async {
    if (_refreshToken == null) return false;
    final res = await http.post(
      Uri.parse('$apiBaseUrl/auth/refresh'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'refresh': _refreshToken}),
    );
    if (res.statusCode != 200) return false;
    _accessToken = _decode(res)['access'] as String;
    await _storage.write(key: 'access_token', value: _accessToken);
    return true;
  }

  Future<http.Response> _authedRequest(
    String method,
    String path, {
    Map<String, String>? query,
    Object? body,
  }) async {
    final uri = Uri.parse('$apiBaseUrl$path').replace(queryParameters: query);

    Future<http.Response> send() {
      final headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $_accessToken',
      };
      if (method == 'GET') return http.get(uri, headers: headers);
      return http.post(uri, headers: headers, body: jsonEncode(body));
    }

    var res = await send();
    if (res.statusCode == 401 && await _refreshAccessToken()) {
      res = await send();
    }
    return res;
  }

  Future<Map<String, dynamic>> fetchMe() async {
    final res = await _authedRequest('GET', '/auth/me');
    if (res.statusCode != 200) {
      throw ApiException('사용자 정보 조회에 실패했습니다. (${res.statusCode})');
    }
    return _decode(res);
  }

  Future<Map<String, dynamic>> fetchParts() async {
    final res = await _authedRequest('GET', '/parts');
    if (res.statusCode != 200) {
      throw ApiException('파트 목록 조회에 실패했습니다. (${res.statusCode})');
    }
    return _decode(res);
  }

  Future<Map<String, dynamic>> fetchInventoryFilters() async {
    final res = await _authedRequest('GET', '/inventory/filters');
    if (res.statusCode != 200) {
      throw ApiException('필터 목록 조회에 실패했습니다. (${res.statusCode})');
    }
    return _decode(res);
  }

  Future<List<dynamic>> searchInventory({
    String q = '',
    String part = '',
    String sort = '',
    String order = '',
    String reagentType = '',
    String vendor = '',
  }) async {
    final res = await _authedRequest(
      'GET',
      '/inventory',
      query: {
        'q': q,
        'part': part,
        'sort': sort,
        'order': order,
        'reagent_type': reagentType,
        'vendor': vendor,
        'limit': '1000',
      },
    );
    if (res.statusCode != 200) {
      throw ApiException('재고 조회에 실패했습니다. (${res.statusCode})');
    }
    return jsonDecode(utf8.decode(res.bodyBytes)) as List<dynamic>;
  }

  Future<String> dispense({required int inventoryId, required int qty}) async {
    final res = await _authedRequest(
      'POST',
      '/dispense',
      body: {'inventory_id': inventoryId, 'qty': qty},
    );
    final data = _decode(res);
    if (res.statusCode != 200) {
      throw ApiException(data['detail'] as String? ?? '출고 처리에 실패했습니다.');
    }
    return data['detail'] as String;
  }

  Future<Map<String, dynamic>> lookupBarcode(String qrContent) async {
    final res = await _authedRequest('GET', '/barcode/lookup', query: {'qr_content': qrContent});
    final data = _decode(res);
    if (res.statusCode != 200) {
      throw ApiException(data['detail'] as String? ?? 'QR 조회에 실패했습니다.');
    }
    return data;
  }

  Future<String> confirmBarcode(String qrContent) async {
    final res = await _authedRequest('POST', '/barcode/confirm', body: {'qr_content': qrContent});
    final data = _decode(res);
    if (res.statusCode != 200) {
      throw ApiException(data['detail'] as String? ?? '출고 처리에 실패했습니다.');
    }
    return data['detail'] as String;
  }
}
