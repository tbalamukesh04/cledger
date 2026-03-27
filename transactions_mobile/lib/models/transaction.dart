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
      amount: json['amount'] != null ? double.tryParse(json['amount'].toString()) : null,
      currency: json['currency'] as String?,
      remarks: json['remarks'] as String?,
      txnDate: json['txn_date'] != null 
          ? DateTime.tryParse(json['txn_date'].toString()) 
          : null,
      status: json['status']?.toString(), // Handle potential enum or string
      // Safely parse confidence whether it arrives as a number or a string
      confidence: json['confidence'] != null 
          ? double.tryParse(json['confidence'].toString()) 
          : null,
      // Provide a fallback of DateTime.now() if the backend omits created_at
      createdAt: json['created_at'] != null 
          ? DateTime.tryParse(json['created_at'].toString()) ?? DateTime.now()
          : DateTime.now(),
      updatedAt: json['updated_at'] != null 
          ? DateTime.tryParse(json['updated_at'].toString()) 
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
