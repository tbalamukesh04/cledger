class Participant {
    final int id;
    final String? name;
    final String phone;

    Participant({
        required this.id,
        this.name,
        required this.phone,
    });

    factory Participant.fromJson(Map<String, dynamic> json) {
        return Participant(
            id: json['id'] as int, 
            name: json['displayname'] as String?,
            phone: json['phone'] as String,
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