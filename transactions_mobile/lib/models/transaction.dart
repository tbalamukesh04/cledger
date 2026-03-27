import 'participant.dart';
import 'message_metadata.dart';

class Transaction {
  final int id;
  final int? rawMessageId;
  final double? amount;
  final String? currency;
  final String? remarks;
  final DateTime? txnDate;
  final String? status;
  final double? confidence;
  final DateTime createdAt;
  final DateTime? updatedAt;
  
  // Nested Objects
  final Participant? participant;
  final MessageMetadata? messageMetadata;

  Transaction({
    required this.id,
    this.rawMessageId,
    this.amount,
    this.currency,
    this.remarks,
    this.txnDate,
    this.status,
    this.confidence,
    required this.createdAt,
    this.updatedAt,
    this.participant,
    this.messageMetadata,
  });

  factory Transaction.fromJson(Map<String, dynamic> json) {
    return Transaction(
      id: json['id'] as int,
      rawMessageId: json['raw_message_id'] as int?,
      // Use num to safely handle both int and double JSON parsing for amount
      amount: json['amount'] != null ? (json['amount'] as num).toDouble() : null,
      currency: json['currency'] as String?,
      remarks: json['remarks'] as String?,
      txnDate: json['txn_date'] != null 
          ? DateTime.parse(json['txn_date'] as String) 
          : null,
      status: json['status']?.toString(), // Handle potential enum or string
      confidence: json['confidence'] != null 
          ? (json['confidence'] as num).toDouble() 
          : null,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: json['updated_at'] != null 
          ? DateTime.parse(json['updated_at'] as String) 
          : null,
      // Nested Parsing
      participant: json['participant'] != null 
          ? Participant.fromJson(json['participant'] as Map<String, dynamic>) 
          : null,
      messageMetadata: json['message_metadata'] != null 
          ? MessageMetadata.fromJson(json['message_metadata'] as Map<String, dynamic>) 
          : null,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'raw_message_id': rawMessageId,
      'amount': amount,
      'currency': currency,
      'remarks': remarks,
      'txn_date': txnDate?.toIso8601String(),
      'status': status,
      'confidence': confidence,
      'created_at': createdAt.toIso8601String(),
      'updated_at': updatedAt?.toIso8601String(),
      // Nested Serialization
      'participant': participant?.toJson(),
      'message_metadata': messageMetadata?.toJson(),
    };
  }
}
