import 'package:flutter/material.dart';
import '../models/transaction.dart';
import '../services/api_service.dart';
import '../services/api_client.dart';
import '../repositories/transaction_repository.dart';
import '../services/csv_export_service.dart';
import '../widgets/loading_state.dart';
import '../widgets/empty_state.dart';
import '../widgets/error_state.dart';
import 'transaction_detail_screen.dart';
import 'transaction_edit_screen.dart';
import 'settings_screen.dart';

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
  String? _errorMessage;

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

    // Pass the ApiService directly
    final apiClient = ApiClient(apiService);
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
    setState(() {
      _errorMessage = null;
    });

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
      print("--> [UI] Background sync failed: $e");
      
      if (mounted) {
        setState(() {
          if (_transactions.isEmpty) {
            _errorMessage = 'Failed to load transactions.\nPlease check your network connection.';
          }
        });

        if (_transactions.isNotEmpty) {
          // Show a subtle indicator that we are in offline mode
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Offline: Showing cached transactions')),
          );
        }
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
    
    setState(() {
      _errorMessage = null;
    });

    try {
      // Use syncTransactions to ensure cache is updated on manual refresh
      final results = await repository.syncTransactions(limit: _limit, offset: 0);
      
      // ONLY update state if the network call was completely successful
      if (mounted) {
        setState(() {
          _transactions = results;
          _offset = results.length;
          _hasMore = results.length >= _limit;
          _errorMessage = null;
        });
      }
    } catch (e) {
      // Fail gracefully: Do not overwrite UI state, retain cached data
      print("--> [UI] Manual refresh failed: $e");
      
      if (mounted) {
        setState(() {
          if (_transactions.isEmpty) {
            _errorMessage = 'Failed to refresh transactions.\nPlease check your network connection.';
          }
        });
        
        if (_transactions.isNotEmpty) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Offline: Cannot refresh right now. Showing cached data.')),
          );
        }
      }
    }
  }

  Future<void> _fetchMoreTransactions() async {
    print("--> [UI] Scroll triggered. offset: $_offset, hasMore: $_hasMore, isFetchingMore: $_isFetchingMore, isLoading: $_isLoading");
    if (_isFetchingMore || !_hasMore || _isLoading) {
      return;
    }

    setState(() {
      _isFetchingMore = true;
    });

    try {
      print("--> [UI] Requesting next batch from repository...");
      final results = await repository.fetchTransactions(limit: _limit, offset: _offset);
      print("--> [UI] Received ${results.length} more transactions.");
      
      setState(() {
        if (results.isEmpty) {
          _hasMore = false;
        } else {
          // Use List.from to ensure a new reference is created, triggering a UI rebuild
          _transactions = List.from(_transactions)..addAll(results);
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
              child: CustomLoadingState.inline(),
            )
          else ...[
            IconButton(
              icon: const Icon(Icons.download),
              onPressed: _exportCsv,
              tooltip: 'Export CSV',
            ),
            IconButton(
              icon: const Icon(Icons.settings),
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => SettingsScreen(
                      onRefreshRequested: _refreshTransactions,
                    ),
                  ),
                );
              },
              tooltip: 'Settings',
            ),
          ],
        ],
      ),
body: AnimatedSwitcher(
        duration: const Duration(milliseconds: 300),
        child: _isLoading && _transactions.isEmpty
            ? const CustomLoadingState.centered(message: 'Loading transactions...')
            : RefreshIndicator(
                onRefresh: _refreshTransactions,
                child: _errorMessage != null && _transactions.isEmpty
                    ? CustomErrorState(
                        message: _errorMessage!,
                        onRetry: _fetchTransactions,
                      )
                    : _transactions.isEmpty
                        ? CustomEmptyState(
                            title: 'No transactions found',
                            message: 'Pull down to refresh or add a new transaction.',
                            actionLabel: 'Refresh',
                            onActionPressed: _refreshTransactions,
                          )
                        : ListView.builder(
                            controller: _scrollController,
                            physics: const AlwaysScrollableScrollPhysics(),
                            itemCount: _transactions.length + (_isFetchingMore ? 1 : 0),
                            itemBuilder: (context, index) {
                              // Display a loading indicator at the bottom if fetching more
                              if (index == _transactions.length) {
                                return const CustomLoadingState.pagination();
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
                              final isPending = txn.syncState == 'pending_local';

                              return Card(
                                margin: const EdgeInsets.symmetric(horizontal: 8.0, vertical: 4.0),
                                child: ListTile(
                                  title: Row(
                                    children: [
                                      if (isPending) const Padding(
                                        padding: EdgeInsets.only(right: 6.0),
                                        child: Icon(Icons.cloud_off, color: Colors.orange, size: 18),
                                      ),
                                      Expanded(
                                        child: Text(
                                          participantName,
                                          style: const TextStyle(fontWeight: FontWeight.bold),
                                        ),
                                      ),
                                    ],
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
                                  onTap: () async {
                                      await Navigator.push(
                                          context, 
                                          MaterialPageRoute(
                                              builder: (context) => TransactionDetailScreen(
                                                  transaction: txn
                                              ),
                                          ),
                                      );
                                      final cached = repository.getCachedTransactions();
                                      final updatedIndex = cached.indexWhere((t) => t.id == txn.id);
                                      
                                      if (updatedIndex != -1 && mounted) {
                                        setState(() {
                                          _transactions[index] = cached[updatedIndex];
                                        });
                                      }
                                  },
                                ),
                              );
                            },
                          ),
              ),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () async {
          // Open TransactionEditScreen in Create Mode (transaction == null)
          final newTxn = await Navigator.push(
            context,
            MaterialPageRoute(
              builder: (context) => const TransactionEditScreen(),
            ),
          );

          // Optimistic UI Update: Instantly refresh the list from the local cache 
          // to show the newly created PENDING_LOCAL transaction without a network request.
          if (newTxn != null && mounted) {
            final cached = repository.getCachedTransactions();
            setState(() {
              _transactions = cached;
              _offset = cached.length;
              _errorMessage = null;
            });
          }
        },
        tooltip: 'Add Transaction',
        child: const Icon(Icons.add),
      ),
    );
  }
}