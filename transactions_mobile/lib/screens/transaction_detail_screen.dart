import 'package:flutter/material.dart';
import '../models/transaction.dart';
import '../services/api_service.dart';
import '../services/api_client.dart';
import '../repositories/transaction_repository.dart';
import 'transaction_edit_screen.dart';

class TransactionDetailScreen extends StatefulWidget {
  final Transaction transaction;

  const TransactionDetailScreen({
    Key? key,
    required this.transaction,
  }) : super(key: key);

  @override
  State<TransactionDetailScreen> createState() => _TransactionDetailScreenState();
}

class _TransactionDetailScreenState extends State<TransactionDetailScreen> {
  late Transaction _transaction;
  late final TransactionRepository repository;
  bool _isRefreshing = false;

  @override
  void initState() {
    super.initState();
    // 1. Initialize with the passed transaction for an instant UI render
    _transaction = widget.transaction;
    
    // 2. Setup repository to fetch fresh data
    final apiService = ApiService();
    const testToken = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxLCJ0ZW5hbnRfaWQiOjEsInJvbGUiOiJhZG1pbiIsImV4cCI6MTgwOTUwOTgyOX0.NnbwMPmiDl1SXSUehEmbN5R-dz3_0PjjaU0v0ekJn4U";
    apiService.client.options.headers['Authorization'] = 'Bearer $testToken';
    final apiClient = ApiClient(apiService.client);
    repository = TransactionRepository(apiClient: apiClient);

    // 3. Optionally fetch latest data in the background on load
    _fetchLatestTransaction();
  }
    
  Future<void> _fetchLatestTransaction() async {
    if (!mounted) return;
    setState(() => _isRefreshing = true);
    
    try {
      final freshData = await repository.fetchTransaction(_transaction.id);
      if (mounted) {
        setState(() {
          _transaction = freshData;
        });
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Viewing cached data. Update failed: $e')),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isRefreshing = false);
      }
    }
  }

  // Helper method for basic date formatting
  String _formatDate(DateTime? date) {
    if (date == null) return 'N/A';
    return "${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')} ${date.hour.toString().padLeft(2, '0')}:${date.minute.toString().padLeft(2, '0')}";
  }

  @override
  Widget build(BuildContext context) {
    // Safely unwrap model properties using the local state _transaction
    final currency = _transaction.currency ?? '';
    final amount = _transaction.amount?.toStringAsFixed(2) ?? '0.00';
    final status = _transaction.status ?? 'Unknown';
    final remarks = _transaction.remarks ?? 'No remarks';
    
    final confidenceText = _transaction.confidence != null 
        ? '${(_transaction.confidence! * 100).toStringAsFixed(1)}%' 
        : 'N/A';
    
    final participantName = _transaction.participant?.name ?? 'Unknown Name';
    final participantPhone = _transaction.participant?.phone ?? 'Unknown Phone';
    
    // Removed the .content fallback since your model doesn't use it
    final messageText = _transaction.messageMetadata?.text ?? 
                        'No message context available'; 

    return Scaffold(
      appBar: AppBar(
        title: Text('Transaction #${_transaction.id}'),
          actions: [
          // Subtle loading indicator in AppBar during background fetch
          if (_isRefreshing)
            const Center(
              child: Padding(
                padding: EdgeInsets.symmetric(horizontal: 16.0),
                child: SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                ),
              ),
            ),
          IconButton(
            icon: const Icon(Icons.edit),
            tooltip: 'Review & Edit Transaction',
            onPressed: () async {
              final updatedTxn = await Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => TransactionEditScreen(transaction: _transaction),
                ),
              );
              
              // If the edit screen pops back with an updated transaction, refresh the UI
              if (updatedTxn != null && updatedTxn is Transaction) {
                setState(() {
                  _transaction = updatedTxn;
                });
              }
            },
          ),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _fetchLatestTransaction,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.all(16.0),
            children: [
              // 1. Core Financial Header
              Card(
                elevation: 2,
                child: Padding(
                  padding: const EdgeInsets.all(24.0),
                  child: Column(
                    children: [
                      Text(
                        '$currency $amount'.trim(),
                        style: const TextStyle(
                          fontSize: 36,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 12),
                      Chip(
                        label: Text(
                          status.toUpperCase(),
                          style: const TextStyle(fontWeight: FontWeight.bold),
                        ),
                        backgroundColor: status.toLowerCase() == 'completed' 
                            ? Colors.green.shade100 
                            : Colors.orange.shade100,
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 24),

              // 2. Transaction Info Section
              _buildSectionHeader('Transaction Info', Icons.receipt_long_outlined),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _buildDetailRow('Txn Date', _formatDate(_transaction.txnDate)),
                      const Divider(),
                      _buildDetailRow('Created At', _formatDate(_transaction.createdAt)),
                      const Divider(),
                      _buildDetailRow('AI Confidence', confidenceText),
                      const Divider(),
                      _buildDetailRow('Remarks', remarks),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // 3. Participant Info Section
              _buildSectionHeader('Participant Info', Icons.person_outline),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _buildDetailRow('Name', participantName),
                      const Divider(),
                      _buildDetailRow('Phone', participantPhone),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // 4. Message Info Section (Ingestion Source)
              _buildSectionHeader('Ingestion Source', Icons.smart_toy_outlined),
              Card(
                color: Colors.grey.shade50,
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Row(
                        children: [
                          Icon(Icons.message_outlined, size: 18, color: Colors.grey),
                          SizedBox(width: 8),
                          Text(
                            'Raw Message Context',
                            style: TextStyle(
                              fontSize: 13,
                              color: Colors.grey,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      Text(
                        messageText,
                        style: const TextStyle(
                          fontSize: 16,
                          fontStyle: FontStyle.italic,
                          height: 1.4,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 24), 
            ],
          ),
        ),
      ),
    );
  }

  // UI Helper for section titles
  Widget _buildSectionHeader(String title, IconData icon) {
    return Padding(
      padding: const EdgeInsets.only(left: 4.0, bottom: 8.0, top: 8.0),
      child: Row(
        children: [
          Icon(icon, size: 22, color: Theme.of(context).primaryColor),
          const SizedBox(width: 8),
          Text(
            title,
            style: const TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
              letterSpacing: 0.3,
            ),
          ),
        ],
      ),
    );
  }

  // UI Helper for key-value rows
  Widget _buildDetailRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6.0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 110,
            child: Text(
              label,
              style: const TextStyle(
                color: Colors.grey,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(
                fontWeight: FontWeight.w500,
                fontSize: 15,
              ),
            ),
          ),
        ],
      ),
    );
  }
}