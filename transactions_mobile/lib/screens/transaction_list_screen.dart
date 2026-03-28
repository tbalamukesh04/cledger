import 'package:flutter/material.dart';
import '../models/transaction.dart';
import '../services/api_service.dart';
import '../services/api_client.dart';
import '../repositories/transaction_repository.dart';
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
  bool _hasMore = true;
  int _offset = 0;
  final int _limit = 50;

  final ScrollController _scrollController = ScrollController();
  late final TransactionRepository repository;

  @override
  void initState() {
    super.initState();
    
    // Initialize API dependencies and repository
    final apiService = ApiService();
    
    // Temporarily inject the test token to resolve the 401 Unauthorized error.
    // TODO: Replace with dynamic token retrieval from secure storage in future steps.
    const testToken = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxLCJ0ZW5hbnRfaWQiOjEsInJvbGUiOiJhZG1pbiIsImV4cCI6MTc3NDc4MDE3NH0.X7n1kaJL_-J8x0bb4IckDpYbXXjKGoGHqzOvQQx6ySE";
    apiService.client.options.headers['Authorization'] = 'Bearer $testToken';

    final apiClient = ApiClient(apiService.client);
    repository = TransactionRepository(apiClient: apiClient);

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
      _isLoading = true;
    });

    try {
      final results = await repository.fetchTransactions(limit: _limit, offset: 0);
      
      setState(() {
        _transactions = results;
        _offset = results.length;
        _hasMore = results.length >= _limit;
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to load transactions: $e')),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _refreshTransactions() async {
    // Reset pagination state
    setState(() {
      _offset = 0;
      _hasMore = true;
    });
    
    try {
      final results = await repository.fetchTransactions(limit: _limit, offset: 0);
      
      setState(() {
        _transactions = results;
        _offset = results.length;
        _hasMore = results.length >= _limit;
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to refresh transactions: $e')),
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Transactions'),
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