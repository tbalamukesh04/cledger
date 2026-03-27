class MessageMetadata {
    final int id;
    final String text;
    final DateTime? timestamp;

    MessageMetadata({
        required this.id,
        required this.text,
        this.timestamp,
    });

    factory MessageMetadata.fromJson(Map<String, dynamic> json) {
        return MessageMetadata(
            id: json['message_id'] as int,
            text: json['raw_text'] as String,
            timestamp: json['received_at'] != null 
            ? DateTime.parse(json['received_at'] as String)
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