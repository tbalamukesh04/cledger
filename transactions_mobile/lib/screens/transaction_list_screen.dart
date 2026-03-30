import 'package:flutter/material.dart';
import '../models/transaction.dart';
import '../services/api_service.dart';
import '../services/api_client.dart';
import '../repositories/transaction_repository.dart';
import '../services/csv_export_service.dart';
import 'transaction_detail_screen.dart';

class TransactionListScreen extends StatefulWidget {
  const TransactionListScreen({super.key});

  @override
  State<TransactionListScreen> createState() => _TransactionListScreenState();
}

class _TransactionListScreenState extends State<TransactionListScreen> {
  // State variables for managing transactions and pagination
  List<Transaction> _transactions = [];
  bool _isLoading = false;
  bool _isFetchingMore = false;
  bool _isSyncing = false;
  bool _isExporting = false;
  bool _hasMore = true;
  int _offset = 0;
  final int _limit = 50;

  final ScrollController _scrollController = ScrollController();
  late final TransactionRepository repository;
  late final CsvExportService _csvExportService;

  @override
  void initState() {
    super.initState();
    
    // Initialize API dependencies and repository
    final apiService = ApiService();
    
    // Temporarily inject the test token to resolve the 401 Unauthorized error.
    // TODO: Replace with dynamic token retrieval from secure storage in future steps.
    const testToken = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxLCJ0ZW5hbnRfaWQiOjEsInJvbGUiOiJhZG1pbiIsImV4cCI6MTc3NDg5MzkzMX0.ZzJoLbdC_TSQyM_4z4h80PlIYhX4bR9Fp-ctPpsrixE";
    apiService.client.options.headers['Authorization'] = 'Bearer $testToken';

    final apiClient = ApiClient(apiService.client);
    repository = TransactionRepository(apiClient: apiClient);
    _csvExportService = CsvExportService(apiClient);

    _scrollController.addListener(_onScroll);
    _fetchTransactions();
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    // If user scrolls near the bottom of the list, trigger a fetch
    if (_scrollController.position.pixels >= _scrollController.position.maxScrollExtent - 200) {
      _fetchMoreTransactions();
    }
  }

Future<void> _fetchTransactions() async {
    // 1. Instantly load from cache to populate the UI immediately
    final cachedTransactions = repository.getCachedTransactions();
    if (cachedTransactions.isNotEmpty) {
      setState(() {
        _transactions = cachedTransactions;
        _offset = cachedTransactions.length;
        _hasMore = cachedTransactions.length >= _limit;
      });
    } else {
      // Only show full loading spinner if cache is completely empty
      setState(() {
        _isLoading = true;
      });
    }

    // 2. Trigger the dedicated background sync
    await _syncInBackground();

    // Turn off loading indicator if it was turned on
    if (mounted && _isLoading) {
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<void> _syncInBackground() async {
    if (_isSyncing) return; // Guard against duplicate calls

    setState(() {
      _isSyncing = true;
    });

    try {
      final fresh = await repository.syncTransactions(limit: _limit, offset: 0);
      if (mounted) {
        setState(() {
          _transactions = fresh;
          _offset = fresh.length;
          _hasMore = fresh.length >= _limit;
        });
      }
    } catch (e) {
      // Fail silently, keep cached data
      print("--> [UI] Background sync failed silently: $e");
      
      if (mounted && _transactions.isNotEmpty) {
        // Show a subtle indicator that we are in offline mode
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Offline: Showing cached transactions')),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _isSyncing = false;
        });
      }
    }
  }

  Future<void> _refreshTransactions() async {
    if (_isSyncing) return; // Prevent manual refresh if already syncing in background

    try {
      // Use syncTransactions to ensure cache is updated on manual refresh
      final results = await repository.syncTransactions(limit: _limit, offset: 0);
      
      // ONLY update state if the network call was completely successful
      if (mounted) {
        setState(() {
          _transactions = results;
          _offset = results.length;
          _hasMore = results.length >= _limit;
        });
      }
    } catch (e) {
      // Fail gracefully: Do not overwrite UI state, retain cached data
      print("--> [UI] Manual refresh failed: $e");
      
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Offline: Cannot refresh right now. Showing cached data.')),
        );
      }
    }
  }

  Future<void> _fetchMoreTransactions() async {
    if (_isFetchingMore || !_hasMore || _isLoading) return;

    setState(() {
      _isFetchingMore = true;
    });

    try {
      final results = await repository.fetchTransactions(limit: _limit, offset: _offset);
      
      setState(() {
        if (results.isEmpty) {
          _hasMore = false;
        } else {
          _transactions.addAll(results);
          _offset += results.length;
          _hasMore = results.length >= _limit;
        }
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to load more transactions: $e')),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _isFetchingMore = false;
        });
      }
    }
  }

Future<void> _exportCsv() async {
    if (_isExporting) return;

    setState(() {
      _isExporting = true;
    });

    try {
      final filePath = await _csvExportService.exportAndSaveCsv();
      
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Exported successfully to:\n$filePath'),
            duration: const Duration(seconds: 5),
            action: SnackBarAction(
              label: 'OK',
              onPressed: () {},
            ),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to export: $e')),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _isExporting = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Transactions'),
        actions: [
          if (_isSyncing || _isExporting)
            const Padding(
              padding: EdgeInsets.all(16.0),
              child: SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                ),
              ),
            )
          else
            IconButton(
              icon: const Icon(Icons.download),
              onPressed: _exportCsv,
              tooltip: 'Export CSV',
            ),
        ],
      ),
      body: _isLoading && _transactions.isEmpty
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _refreshTransactions,
              child: _transactions.isEmpty
                  ? ListView(
                      physics: const AlwaysScrollableScrollPhysics(),
                      children: const [
                        SizedBox(height: 200),
                        Center(child: Text('No transactions found. Pull down to refresh.')),
                      ],
                    )
                  : ListView.builder(
                      controller: _scrollController,
                      physics: const AlwaysScrollableScrollPhysics(),
                      itemCount: _transactions.length + (_isFetchingMore ? 1 : 0),
                      itemBuilder: (context, index) {
                        // Display a loading indicator at the bottom if fetching more
                        if (index == _transactions.length) {
                          return const SafeArea(
                            top: false,
                            child: Padding(
                                padding: EdgeInsets.all(16.0),
                                child: Center(child: CircularProgressIndicator()),
                            ),
                          );
                        }

                        final txn = _transactions[index];
                        
                        final currency = txn.currency ?? '';
                        final amount = txn.amount?.toStringAsFixed(2) ?? '0.00';
                        final participantName = txn.participant?.name ?? 
                                                txn.participant?.phone ?? 
                                                'Unknown Participant';
                        final dateStr = txn.txnDate != null 
                            ? "${txn.txnDate!.year}-${txn.txnDate!.month.toString().padLeft(2, '0')}-${txn.txnDate!.day.toString().padLeft(2, '0')}"
                            : "Unknown Date";
                        final status = txn.status ?? 'Unknown';

                        return Card(
                          margin: const EdgeInsets.symmetric(horizontal: 8.0, vertical: 4.0),
                          child: ListTile(
                            title: Text(
                              participantName,
                              style: const TextStyle(fontWeight: FontWeight.bold),
                            ),
                            subtitle: Text('$dateStr\nStatus: $status'),
                            isThreeLine: true,
                            trailing: Text(
                              '$currency $amount'.trim(),
                              style: const TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            onTap: () {
                                Navigator.push(
                                    context, 
                                    MaterialPageRoute(
                                        builder: (context) => TransactionDetailScreen(
                                            transaction: txn
                                        ),
                                    ),
                                );
                            },
                          ),
                        );
                      },
                    ),
            ),
    );
  }
}