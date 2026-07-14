// 서버 주소는 이 한 곳에서만 관리합니다.
// 지금은 개발용 PC의 Tailscale IP를 씁니다 (병원 유선랜과 폰 와이파이 대역이
// 분리돼 있어 일반 LAN IP로는 접속이 안 되고, Tailscale이 이를 우회해줍니다).
// 다른 서버로 옮길 때는 아래 기본값을 바꾸거나,
// `flutter run --dart-define=API_BASE_URL=https://new-server.example.com/api` 로 덮어씁니다.
const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://100.84.170.54:8000/api',
);
