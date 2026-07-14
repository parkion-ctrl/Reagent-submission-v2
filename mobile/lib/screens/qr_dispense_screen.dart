import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../api_client.dart';

class QrDispenseScreen extends StatefulWidget {
  final ApiClient apiClient;
  const QrDispenseScreen({super.key, required this.apiClient});

  @override
  State<QrDispenseScreen> createState() => _QrDispenseScreenState();
}

class _QrDispenseScreenState extends State<QrDispenseScreen> {
  final MobileScannerController _controller = MobileScannerController();
  bool _busy = false;

  Future<void> _onDetect(BarcodeCapture capture) async {
    if (_busy || capture.barcodes.isEmpty) return;
    final code = capture.barcodes.first.rawValue;
    if (code == null || code.isEmpty) return;

    setState(() => _busy = true);
    await _controller.stop();
    try {
      final info = await widget.apiClient.lookupBarcode(code);
      if (!mounted) return;
      final confirmed = await _showConfirmSheet(info);
      if (confirmed == true) {
        final message = await widget.apiClient.confirmBarcode(code);
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString())));
      }
    } finally {
      if (mounted) {
        setState(() => _busy = false);
        await _controller.start();
      }
    }
  }

  Future<bool?> _showConfirmSheet(Map<String, dynamic> info) {
    return showModalBottomSheet<bool>(
      context: context,
      isDismissible: true,
      showDragHandle: true,
      builder: (ctx) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${info['item_name']}',
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 8),
                Text('${info['item_code']}  ·  Lot ${info['lot_no']}'),
                Text('유효기한 ${info['expiry_date'] ?? '-'}'),
                Text('현재 재고 ${info['current_stock']} ${info['unit'] ?? ''}'),
                const SizedBox(height: 20),
                const Text('1개를 출고 처리하시겠습니까?'),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton(
                        onPressed: () => Navigator.of(ctx).pop(false),
                        child: const Text('취소'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: FilledButton(
                        onPressed: () => Navigator.of(ctx).pop(true),
                        child: const Text('출고 확인'),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('QR 출고 (테스트)'), centerTitle: true),
      body: Stack(
        fit: StackFit.expand,
        children: [
          MobileScanner(controller: _controller, onDetect: _onDetect),
          Align(
            alignment: Alignment.topCenter,
            child: Container(
              margin: const EdgeInsets.only(top: 16),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.55),
                borderRadius: BorderRadius.circular(20),
              ),
              child: const Text('QR 코드를 화면 안에 맞춰주세요', style: TextStyle(color: Colors.white)),
            ),
          ),
          if (_busy)
            Container(
              color: Colors.black.withValues(alpha: 0.3),
              child: const Center(child: CircularProgressIndicator()),
            ),
        ],
      ),
    );
  }
}
