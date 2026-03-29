import 'package:hive/hive.dart';

part 'message_metadata.g.dart';
@HiveType(typeId: 2)
class MessageMetadata {
    @HiveField(0)
    final int id;
    @HiveField(1)
    final String text;
    @HiveField(2)
    final DateTime? timestamp;

    MessageMetadata({
        required this.id,
        required this.text,
        this.timestamp,
    });

    factory MessageMetadata.fromJson(Map<String, dynamic> json) {
        return MessageMetadata(
            // Use ?? to provide a safe fallback if id is null
            id: json['message_id'] != null ? int.parse(json['message_id'].toString()) : 0,
            // Provide a safe fallback string if raw_text is missing
            text: json['raw_text']?.toString() ?? 'No text available',
            timestamp: json['received_at'] != null 
                ? DateTime.tryParse(json['received_at'].toString())
                : null,
        );
    }

    Map<String, dynamic> toJson() {
        return {
            'message_id': id,
            'raw_text': text,
            'received_at': timestamp?.toIso8601String(),
        };
    }
}