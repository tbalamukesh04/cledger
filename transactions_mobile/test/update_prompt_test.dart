import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/mockito.dart';
import 'package:mockito/annotations.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:transactions_mobile/models/update_metadata.dart';
import 'package:transactions_mobile/services/api_client.dart';
import 'package:transactions_mobile/services/version_service.dart';

// Generate MockApiClient via build_runner
import 'update_prompt_test.mocks.dart';

@GenerateNiceMocks([MockSpec<ApiClient>()])
void main() {
  late MockApiClient mockApiClient;
  late VersionService versionService;

  // Set up static PackageInfo platform state matching existing configuration
  setUpAll(() {
    PackageInfo.setMockInitialValues(
      appName: 'Cledger',
      packageName: 'com.example.transactions_mobile',
      version: '1.0.0',
      buildNumber: '1',
      buildSignature: 'test_sig',
    );
  });

  setUp(() {
    mockApiClient = MockApiClient();
    versionService = VersionService(mockApiClient);
  });

  group('VersionService Evaluation Scenarios', () {
    test('Scenario 1: App is already at the latest version', () async {
      final metadata = UpdateMetadata(
        latestVersion: '1.0.0',
        buildNumber: 1,
        minRequiredVersion: '1.0.0',
        forceUpdate: false,
        downloadUrl: 'https://api.cledger.com/app.apk',
        releaseNotes: ['Initial MVP release'],
      );

      when(mockApiClient.fetchLatestAppVersion()).thenAnswer((_) async => metadata);

      final result = await versionService.checkForUpdates();

      expect(result.hasUpdate, isFalse);
      expect(result.requirement, equals(UpdateRequirement.none));
    });

    test('Scenario 2: Optional update available via build number bump', () async {
      final metadata = UpdateMetadata(
        latestVersion: '1.0.0',
        buildNumber: 2, // Remote build > native build
        minRequiredVersion: '1.0.0',
        forceUpdate: false,
        downloadUrl: 'https://api.cledger.com/app.apk',
        releaseNotes: ['Minor bug fixes'],
      );

      when(mockApiClient.fetchLatestAppVersion()).thenAnswer((_) async => metadata);

      final result = await versionService.checkForUpdates();

      expect(result.hasUpdate, isTrue);
      expect(result.requirement, equals(UpdateRequirement.optional));
    });

    test('Scenario 3: Force update triggered via explicit backend flag', () async {
      final metadata = UpdateMetadata(
        latestVersion: '1.1.0',
        buildNumber: 3,
        minRequiredVersion: '1.0.0',
        forceUpdate: true, // Forces critical update path
        downloadUrl: 'https://api.cledger.com/app.apk',
        releaseNotes: ['Security patches'],
      );

      when(mockApiClient.fetchLatestAppVersion()).thenAnswer((_) async => metadata);

      final result = await versionService.checkForUpdates();

      expect(result.hasUpdate, isTrue);
      expect(result.requirement, equals(UpdateRequirement.mandatory));
    });

    test('Scenario 3b: Force update triggered via minRequiredVersion breach', () async {
      // Set native version behind minimum boundary
      PackageInfo.setMockInitialValues(
        appName: 'Cledger',
        packageName: 'com.example.transactions_mobile',
        version: '0.9.0',
        buildNumber: '1',
        buildSignature: 'test_sig',
      );

      final metadata = UpdateMetadata(
        latestVersion: '1.0.0',
        buildNumber: 2,
        minRequiredVersion: '1.0.0', // Breaches native 0.9.0
        forceUpdate: false,
        downloadUrl: 'https://api.cledger.com/app.apk',
        releaseNotes: ['Structural upgrades'],
      );

      when(mockApiClient.fetchLatestAppVersion()).thenAnswer((_) async => metadata);

      final result = await versionService.checkForUpdates();

      expect(result.hasUpdate, isTrue);
      expect(result.requirement, equals(UpdateRequirement.mandatory));

      // Reset mock values to default state
      PackageInfo.setMockInitialValues(
        appName: 'Cledger',
        packageName: 'com.example.transactions_mobile',
        version: '1.0.0',
        buildNumber: '1',
        buildSignature: 'test_sig',
      );
    });

    test('Scenario 4: Unreachable endpoint gracefully fails without crashes', () async {
      when(mockApiClient.fetchLatestAppVersion()).thenThrow(Exception('Connection timed out'));

      final result = await versionService.checkForUpdates();

      // Guarantees silent fallback allowing offline initialization flows
      expect(result.hasUpdate, isFalse);
      expect(result.requirement, equals(UpdateRequirement.none));
    });

    test('Scenario 5: Malformed metadata payload parses safely using defaults', () {
      final malformedJson = {
        'latest_version': null,
        'build_number': 'invalid_int',
        'force_update': 'true', // String boolean representation
      };

      final parsed = UpdateMetadata.fromJson(malformedJson);

      expect(parsed.latestVersion, equals('1.0.0')); // Fallback string
      expect(parsed.buildNumber, equals(1)); // Fallback int parsing
      expect(parsed.forceUpdate, isTrue); // String cast mapping
    });
  });
}