import 'package:hive/hive.dart';
part 'participant.g.dart';
@HiveType(typeId: 1)
class Participant {
    @HiveField(0)
    final int id;
    @HiveField(1)
    final String? name;
    @HiveField(2)
    final String phone;

    Participant({
        required this.id,
        this.name,
        required this.phone,
    });

    factory Participant.fromJson(Map<String, dynamic> json) {
        return Participant(
            // Use ?? to provide a safe fallback if id is null
            id: json['id'] != null ? int.parse(json['id'].toString()) : 0, 
            name: json['displayname']?.toString(),
            // Provide a safe fallback string if phone is missing
            phone: json['phone']?.toString() ?? 'Unknown Phone',
        );
    }

    Map<String, dynamic> toJson() {
        return {
            'id': id,
            'displayname': name,
            'phone': phone,
        };
    }
}