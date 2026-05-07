import 'package:flutter/material.dart';
import '../models/transaction.dart';
import '../services/api_service.dart';
import '../services/api_client.dart';
import '../repositories/transaction_repository.dart';

enum ReviewAction { correct, invalidate }

class TransactionEditScreen extends StatefulWidget {
  final Transaction? transaction;

  const TransactionEditScreen({
    Key? key,
    this.transaction,
  }) : super(key: key);

  @override
  State<TransactionEditScreen> createState() => _TransactionEditScreenState();
}

class _TransactionEditScreenState extends State<TransactionEditScreen> {
  final _formKey = GlobalKey<FormState>();
  
  late TransactionRepository _repository;
  bool _isLoading = false;

  late TextEditingController _amountController;
  late TextEditingController _currencyController;
  late TextEditingController _remarksController;
  late TextEditingController _counterpartyController;
  
  String _transactionType = 'debit';
  DateTime? _selectedDate;

  bool get _isCreateMode => widget.transaction == null;

  @override
  void initState() {
    super.initState();
    
    // Setup repository identically to the Detail Screen
    final apiService = ApiService();
    // TODO: Replace with secure token retrieval in future phases
    const testToken = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxLCJ0ZW5hbnRfaWQiOjEsInJvbGUiOiJhZG1pbiIsImV4cCI6MTgwOTUwOTgyOX0.NnbwMPmiDl1SXSUehEmbN5R-dz3_0PjjaU0v0ekJn4U";
    
    apiService.setAuthToken(testToken);
    final apiClient = ApiClient(apiService);
    _repository = TransactionRepository(apiClient: apiClient);

    final txn = widget.transaction;
    final txnJson = txn?.toJson() ?? {}; // Use JSON serialization to safely access fields
    
    _amountController = TextEditingController(text: txn?.amount?.toString() ?? '');
    _currencyController = TextEditingController(text: txn?.currency ?? '');
    _remarksController = TextEditingController(text: txn?.remarks ?? '');
    _counterpartyController = TextEditingController(text: txnJson['counterparty']?.toString() ?? '');
    _selectedDate = txn?.txnDate ?? DateTime.now();

    final typeFromJson = txnJson['txn_type']?.toString().toLowerCase();
    if (typeFromJson == 'credit' || typeFromJson == 'debit') {
      _transactionType = typeFromJson!;
    }
  }

  @override
  void dispose() {
    _amountController.dispose();
    _currencyController.dispose();
    _remarksController.dispose();
    _counterpartyController.dispose();
    super.dispose();
  }

  Future<void> _submitCreate() async {
    FocusScope.of(context).unfocus();
    if (!_formKey.currentState!.validate()) return;
    
    setState(() => _isLoading = true);

    try {
      final safeAmountText = _amountController.text.replaceAll(',', '.');
      
      final newJson = {
        'amount': double.tryParse(safeAmountText),
        'currency': _currencyController.text.trim().toUpperCase(),
        'remarks': _remarksController.text.trim(),
        'counterparty': _counterpartyController.text.trim(),
        'txn_type': _transactionType,
        'txn_date': _selectedDate?.toIso8601String() ?? DateTime.now().toIso8601String(),
      };

      final newTxn = Transaction.fromJson(newJson);
      final savedTxn = await _repository.createTransaction(newTxn);

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Transaction created locally!'), backgroundColor: Colors.blue),
        );
        Navigator.pop(context, savedTxn);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Local creation failed: $e'), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _submitReview(ReviewAction action) async {
    // 1. Force the keyboard to dismiss so the user sees the bottom buttons
    FocusScope.of(context).unfocus();

    // Only validate the form if the action is correct
    if (action == ReviewAction.correct && !_formKey.currentState!.validate()) {
      print("❌ Form validation failed.");
      return;
    }

    setState(() => _isLoading = true);

    try {
      Map<String, dynamic>? correctedFields;
      
      if (action == ReviewAction.correct) {
        // 2. Safely handle international keyboards that use commas for decimals
        final safeAmountText = _amountController.text.replaceAll(',', '.');
        
        correctedFields = {
          'amount': double.tryParse(safeAmountText),
          'currency': _currencyController.text.trim().toUpperCase(),
          'remarks': _remarksController.text.trim(),
          'counterparty': _counterpartyController.text.trim(),
          'txn_type': _transactionType,
          if (_selectedDate != null) 'txn_date': _selectedDate!.toIso8601String(), 
        };
        
        correctedFields.removeWhere((key, value) => value == null);
      }

      final actionString = action == ReviewAction.correct ? 'correct' : 'invalidate';
      
      // 3. Print the exact payload to the Flutter terminal for debugging
      print("🚀 Submitting API Request...");
      print("   URL: /transactions/${widget.transaction!.id}/review");
      print("   Action: $actionString");
      print("   Payload: $correctedFields");
      
      final updatedTransaction = await _repository.reviewTransaction(
        widget.transaction!.id, 
        actionString,
        correctedFields: correctedFields,
      );
      
      print("✅ Successfully received response from backend.");

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Transaction updated successfully!'), backgroundColor: Colors.green),
        );
        Navigator.pop(context, updatedTransaction);
      }
    } catch (e) {
      print("🔴 API Call Failed: $e");
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Update failed. Reverted to previous state: $e'), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_isCreateMode ? 'Create Transaction' : 'Edit Transaction #${widget.transaction!.id}'),
      ),
      body: SafeArea(
        child: _isLoading
            ? const Center(child: CircularProgressIndicator())
            : SingleChildScrollView(
                padding: const EdgeInsets.all(16.0),
                child: Form(
                  key: _formKey,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      // AMOUNT & CURRENCY ROW
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            flex: 2,
                            child: TextFormField(
                              controller: _amountController,
                              decoration: const InputDecoration(labelText: 'Amount', border: OutlineInputBorder()),
                              keyboardType: const TextInputType.numberWithOptions(decimal: true),
                              validator: (value) {
                                if (value == null || value.trim().isEmpty) return 'Required';
                                // Safely handle international comma decimals during validation
                                final safeAmountText = value.replaceAll(',', '.');
                                if (double.tryParse(safeAmountText) == null) return 'Invalid numeric amount';
                                return null;
                              },
                            ),
                          ),
                          const SizedBox(width: 16),
                          Expanded(
                            flex: 1,
                            child: TextFormField(
                              controller: _currencyController,
                              decoration: const InputDecoration(labelText: 'Currency', border: OutlineInputBorder()),
                              validator: (value) {
                                if (value == null || value.trim().isEmpty) return 'Required';
                                return null;
                              },
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),
                      
                      // TRANSACTION TYPE & COUNTERPARTY ROW
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: DropdownButtonFormField<String>(
                              value: _transactionType,
                              decoration: const InputDecoration(labelText: 'Type', border: OutlineInputBorder()),
                              items: const [
                                DropdownMenuItem(value: 'debit', child: Text('Debit')),
                                DropdownMenuItem(value: 'credit', child: Text('Credit')),
                              ],
                              onChanged: (val) {
                                if (val != null) setState(() => _transactionType = val);
                              },
                            ),
                          ),
                          const SizedBox(width: 16),
                          Expanded(
                            child: TextFormField(
                              controller: _counterpartyController,
                              decoration: const InputDecoration(labelText: 'Counterparty (Opt)', border: OutlineInputBorder()),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),

                      TextFormField(
                        controller: _remarksController,
                        decoration: const InputDecoration(labelText: 'Remarks / Description', border: OutlineInputBorder()),
                        maxLines: 3,
                        validator: (value) {
                          if (value == null || value.trim().isEmpty) return 'Description is required';
                          return null;
                        },
                      ),
                      const SizedBox(height: 16),

                      ListTile(
                        shape: RoundedRectangleBorder(
                          side: BorderSide(color: Colors.grey.shade400, width: 1),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        title: const Text('Transaction Date'),
                        subtitle: Text(_selectedDate != null
                            ? "${_selectedDate!.year}-${_selectedDate!.month.toString().padLeft(2, '0')}-${_selectedDate!.day.toString().padLeft(2, '0')}"
                            : 'Select Date'),
                        trailing: const Icon(Icons.calendar_today),
                        onTap: () async {
                          final picked = await showDatePicker(
                            context: context,
                            initialDate: _selectedDate ?? DateTime.now(),
                            firstDate: DateTime(2000),
                            lastDate: DateTime(2100),
                          );
                          if (picked != null) {
                            setState(() {
                              _selectedDate = picked;
                            });
                          }
                        },
                      ),
                      const SizedBox(height: 32),
                      
                      // DYNAMIC ACTION BUTTONS
                      if (_isCreateMode)
                        ElevatedButton.icon(
                          onPressed: _submitCreate,
                          icon: const Icon(Icons.save),
                          label: const Text('Save Local Transaction'),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: Colors.blue,
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.symmetric(vertical: 16),
                          ),
                        )
                      else
                        Row(
                          children: [
                            Expanded(
                              child: OutlinedButton.icon(
                                onPressed: () => _submitReview(ReviewAction.invalidate),
                                icon: const Icon(Icons.close),
                                label: const Text('Invalidate'),
                                style: OutlinedButton.styleFrom(
                                  foregroundColor: Colors.red,
                                  side: const BorderSide(color: Colors.red),
                                  padding: const EdgeInsets.symmetric(vertical: 16),
                                ),
                              ),
                            ),
                            const SizedBox(width: 16),
                            Expanded(
                              child: ElevatedButton.icon(
                                onPressed: () => _submitReview(ReviewAction.correct),
                                icon: const Icon(Icons.check),
                                label: const Text('Correct'),
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: Colors.green,
                                  foregroundColor: Colors.white,
                                  padding: const EdgeInsets.symmetric(vertical: 16),
                                ),
                              ),
                            ),
                          ],
                        ),
                    ],
                  ),
                ),
              ),
      ),
    );
  }
}