import 'dart:async';

import 'package:flutter/material.dart';

import '../api_client.dart';
import '../part_colors.dart';
import '../widgets/app_drawer.dart';
import '../widgets/logout_button.dart';

class InventoryScreen extends StatefulWidget {
  final ApiClient apiClient;
  final Map<String, dynamic> user;
  const InventoryScreen({super.key, required this.apiClient, required this.user});

  @override
  State<InventoryScreen> createState() => _InventoryScreenState();
}

enum _SortOption { name, stock, expiry }

const _sortLabels = {
  _SortOption.name: '이름순',
  _SortOption.stock: '수량순',
  _SortOption.expiry: '유효기간순',
};

const _sortFields = {
  _SortOption.name: 'item_name',
  _SortOption.stock: 'current_stock',
  _SortOption.expiry: 'expiry_date',
};

class _PickerItem {
  final String value;
  final String label;
  const _PickerItem(this.value, this.label);
}

class _InventoryScreenState extends State<InventoryScreen> {
  final _searchController = TextEditingController();
  Timer? _debounce;
  List<dynamic> _items = [];
  Map<String, dynamic> _parts = {};
  String _selectedPart = '';
  _SortOption? _sort;
  String _order = 'asc';
  Map<String, dynamic>? _filterOptions;
  String _selectedReagentType = '';
  String _selectedReagentTypeLabel = '';
  String _selectedVendor = '';
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadParts();
    _loadFilters();
    _search();
  }

  Future<void> _loadParts() async {
    try {
      final parts = await widget.apiClient.fetchParts();
      if (mounted) setState(() => _parts = parts);
    } catch (_) {
      // 파트 목록이 없어도 검색 자체는 계속 가능하므로 무시
    }
  }

  Future<void> _loadFilters() async {
    try {
      final options = await widget.apiClient.fetchInventoryFilters();
      if (mounted) setState(() => _filterOptions = options);
    } catch (_) {
      // 필터 목록이 없어도 검색 자체는 계속 가능하므로 무시
    }
  }

  Future<void> _search() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final items = await widget.apiClient.searchInventory(
        q: _searchController.text.trim(),
        part: _selectedPart,
        sort: _sort == null ? '' : _sortFields[_sort]!,
        order: _sort == null ? '' : _order,
        reagentType: _selectedReagentType,
        vendor: _selectedVendor,
      );
      if (mounted) setState(() => _items = items);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _showPicker({
    required String title,
    required List<_PickerItem> items,
    required void Function(_PickerItem) onSelected,
  }) async {
    await showModalBottomSheet(
      context: context,
      showDragHandle: true,
      builder: (ctx) {
        return SafeArea(
          child: ListView(
            shrinkWrap: true,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                child: Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
              ),
              for (final it in items)
                ListTile(
                  title: Text(it.label),
                  onTap: () {
                    Navigator.of(ctx).pop();
                    onSelected(it);
                  },
                ),
            ],
          ),
        );
      },
    );
  }

  void _pickReagentType() {
    final options = (_filterOptions?['reagent_types'] as List<dynamic>? ?? [])
        .map((e) => _PickerItem(e['value'] as String, e['label'] as String))
        .toList();
    _showPicker(
      title: '시약 구분 선택',
      items: [const _PickerItem('', '전체'), ...options],
      onSelected: (it) {
        setState(() {
          _selectedReagentType = it.value;
          _selectedReagentTypeLabel = it.value.isEmpty ? '' : it.label;
        });
        _search();
      },
    );
  }

  void _pickVendor() {
    final options = (_filterOptions?['vendors'] as List<dynamic>? ?? [])
        .map((e) => _PickerItem(e as String, e))
        .toList();
    _showPicker(
      title: '업체 선택',
      items: [const _PickerItem('', '전체'), ...options],
      onSelected: (it) {
        setState(() => _selectedVendor = it.value);
        _search();
      },
    );
  }

  void _onSearchChanged(String _) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 400), _search);
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('재고 조회'),
        centerTitle: true,
        actions: [LogoutButton(apiClient: widget.apiClient)],
      ),
      drawer: AppDrawer(apiClient: widget.apiClient, user: widget.user, current: AppSection.inventory),
      body: Column(
        children: [
          Container(
            color: colorScheme.primary,
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            child: Column(
              children: [
                TextField(
                  controller: _searchController,
                  decoration: const InputDecoration(
                    labelText: '품목명 / 코드 / Lot No 검색',
                    prefixIcon: Icon(Icons.search),
                  ),
                  onChanged: _onSearchChanged,
                  onSubmitted: (_) => _search(),
                ),
                if (_parts.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  DropdownButtonFormField<String>(
                    initialValue: _selectedPart,
                    decoration: const InputDecoration(labelText: '파트'),
                    items: [
                      const DropdownMenuItem(value: '', child: Text('전체')),
                      ..._parts.entries.map(
                        (e) => DropdownMenuItem(value: e.key, child: Text('${e.key} (${e.value})')),
                      ),
                    ],
                    onChanged: (value) {
                      setState(() => _selectedPart = value ?? '');
                      _search();
                    },
                  ),
                ],
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 0),
            child: SizedBox(
              height: 36,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: _SortOption.values.map((opt) {
                  final selected = _sort == opt;
                  return Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      showCheckmark: false,
                      label: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(_sortLabels[opt]!),
                          if (selected) ...[
                            const SizedBox(width: 4),
                            Text(_order == 'asc' ? '▽' : '△', style: const TextStyle(fontSize: 11)),
                          ],
                        ],
                      ),
                      selected: selected,
                      onSelected: (_) {
                        setState(() {
                          if (_sort == opt) {
                            _order = _order == 'asc' ? 'desc' : 'asc';
                          } else {
                            _sort = opt;
                            _order = 'asc';
                          }
                        });
                        _search();
                      },
                    ),
                  );
                }).toList(),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 0),
            child: Row(
              children: [
                Expanded(
                  child: _FilterBox(
                    label: '시약 구분',
                    value: _selectedReagentTypeLabel.isEmpty ? '전체' : _selectedReagentTypeLabel,
                    active: _selectedReagentType.isNotEmpty,
                    onTap: _pickReagentType,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: _FilterBox(
                    label: '업체',
                    value: _selectedVendor.isEmpty ? '전체' : _selectedVendor,
                    active: _selectedVendor.isNotEmpty,
                    onTap: _pickVendor,
                  ),
                ),
              ],
            ),
          ),
          if (_error != null)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              margin: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: colorScheme.errorContainer,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(_error!, style: TextStyle(color: colorScheme.onErrorContainer)),
            ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : RefreshIndicator(
                    onRefresh: _search,
                    child: _items.isEmpty
                        ? ListView(
                            children: [
                              Padding(
                                padding: const EdgeInsets.only(top: 80),
                                child: Center(
                                  child: Text(
                                    '검색 결과가 없습니다.',
                                    style: TextStyle(color: colorScheme.onSurfaceVariant),
                                  ),
                                ),
                              ),
                            ],
                          )
                        : ListView.separated(
                            padding: const EdgeInsets.all(12),
                            itemCount: _items.length,
                            separatorBuilder: (_, _) => const SizedBox(height: 10),
                            itemBuilder: (context, index) {
                              final item = _items[index] as Map<String, dynamic>;
                              final isShort = item['status'] == '부족';
                              final brightness = Theme.of(context).brightness;
                              final normalColor = brightness == Brightness.dark
                                  ? const Color(0xFF7BD87F)
                                  : const Color(0xFF2E7D32);
                              final statusColor = isShort ? colorScheme.error : normalColor;
                              final fillColor = partColorFor(item['part'] as String?, brightness);
                              final nameColor = readableTextOn(fillColor);
                              final subColor = nameColor.withValues(alpha: 0.75);
                              return Card(
                                clipBehavior: Clip.antiAlias,
                                child: IntrinsicHeight(
                                  child: Row(
                                    crossAxisAlignment: CrossAxisAlignment.stretch,
                                    children: [
                                      Expanded(
                                        flex: 2,
                                        child: Container(
                                          color: fillColor,
                                          padding: const EdgeInsets.all(14),
                                          child: Column(
                                            crossAxisAlignment: CrossAxisAlignment.start,
                                            mainAxisAlignment: MainAxisAlignment.center,
                                            children: [
                                              Text(
                                                '${item['item_name']}',
                                                style: TextStyle(
                                                  fontWeight: FontWeight.w700,
                                                  fontSize: 15,
                                                  color: nameColor,
                                                ),
                                              ),
                                              const SizedBox(height: 4),
                                              Text(
                                                '${item['item_code']}  ·  Lot ${item['lot_no'] ?? '-'}',
                                                style: TextStyle(fontSize: 12.5, color: subColor),
                                              ),
                                              Text(
                                                '유효기한 ${item['expiry_date'] ?? '-'}',
                                                style: TextStyle(fontSize: 12.5, color: subColor),
                                              ),
                                            ],
                                          ),
                                        ),
                                      ),
                                      Expanded(
                                        child: Container(
                                          padding: const EdgeInsets.all(14),
                                          alignment: Alignment.center,
                                          child: Column(
                                            mainAxisAlignment: MainAxisAlignment.center,
                                            crossAxisAlignment: CrossAxisAlignment.center,
                                            children: [
                                              Text(
                                                '${item['current_stock']} ${item['unit'] ?? ''}',
                                                style: TextStyle(
                                                  fontWeight: FontWeight.w800,
                                                  fontSize: 16,
                                                  color: statusColor,
                                                ),
                                              ),
                                              const SizedBox(height: 4),
                                              Container(
                                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                                decoration: BoxDecoration(
                                                  color: statusColor.withValues(alpha: 0.12),
                                                  borderRadius: BorderRadius.circular(20),
                                                ),
                                                child: Text(
                                                  item['status'] as String? ?? '',
                                                  style: TextStyle(
                                                    fontSize: 11.5,
                                                    fontWeight: FontWeight.w600,
                                                    color: statusColor,
                                                  ),
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              );
                            },
                          ),
                  ),
          ),
        ],
      ),
    );
  }
}

class _FilterBox extends StatelessWidget {
  final String label;
  final String value;
  final bool active;
  final VoidCallback onTap;

  const _FilterBox({required this.label, required this.value, required this.active, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final fg = active ? colorScheme.onPrimaryContainer : colorScheme.onSurfaceVariant;
    return InkWell(
      borderRadius: BorderRadius.circular(12),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: active ? colorScheme.primaryContainer : colorScheme.surfaceContainerHigh,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(
                '$label: $value',
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: fg),
              ),
            ),
            Icon(Icons.arrow_drop_down, size: 18, color: fg),
          ],
        ),
      ),
    );
  }
}
