import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects

ApplicationWindow {
    id: window
    width: 1180
    height: 760
    minimumWidth: 900
    minimumHeight: 620
    visible: true
    title: appBridge.appName + " — Download Manager"
    color: "#090f1d"

    property color panel: "#172238"
    property color muted: "#91a0b8"
    property color accent: "#65d6c4"

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#101b32" }
            GradientStop { position: 0.55; color: "#0b1426" }
            GradientStop { position: 1.0; color: "#090f1d" }
        }
    }

    Rectangle {
        width: 520
        height: 520
        radius: 260
        x: parent.width - width * 0.55
        y: -height * 0.42
        opacity: 0.16
        color: "#477ce8"
        layer.enabled: true
        layer.effect: MultiEffect {
            blurEnabled: true
            blur: 1.0
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 16

        Rectangle {
            Layout.preferredWidth: 220
            Layout.fillHeight: true
            radius: 22
            color: "#b817263d"
            border.color: "#35ffffff"
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 18
                spacing: 18

                RowLayout {
                    spacing: 11
                    Rectangle {
                        width: 42; height: 42; radius: 14
                        gradient: Gradient {
                            GradientStop { position: 0; color: "#72e2cf" }
                            GradientStop { position: 1; color: "#4389dc" }
                        }
                        Text {
                            anchors.centerIn: parent
                            text: "A"
                            color: "#071522"
                            font.pixelSize: 24
                            font.bold: true
                        }
                    }
                    ColumnLayout {
                        spacing: 1
                        Label { text: "ADM"; color: "white"; font.pixelSize: 20; font.bold: true }
                        Label { text: "DOWNLOAD MANAGER"; color: "#91a0b8"; font.pixelSize: 9; font.letterSpacing: 1.4 }
                    }
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: "#24ffffff" }

                Label { text: "WORKSPACE"; color: "#71839f"; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.5 }

                Repeater {
                    model: [
                        { label: "Overview", glyph: "⌂" },
                        { label: "All downloads", glyph: "↓" },
                        { label: "In progress", glyph: "◷" },
                        { label: "Completed", glyph: "✓" },
                        { label: "Scheduler", glyph: "◴" }
                    ]
                    delegate: Rectangle {
                        Layout.fillWidth: true
                        height: 46
                        radius: 13
                        color: index === 0 ? "#3159a8b5" : "transparent"
                        border.color: index === 0 ? "#5265d6c4" : "transparent"
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 13
                            spacing: 13
                            Label { text: modelData.glyph; color: index === 0 ? "#78e4d0" : "#a6b4c9"; font.pixelSize: 19; Layout.preferredWidth: 20 }
                            Label { text: modelData.label; color: index === 0 ? "white" : "#a6b4c9"; font.pixelSize: 13; font.bold: index === 0 }
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                Rectangle {
                    Layout.fillWidth: true
                    radius: 14
                    color: "#1bffffff"
                    border.color: "#25ffffff"
                    height: 82
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 4
                        Label { text: "ENGINE STATUS"; color: "#7f91ad"; font.pixelSize: 9; font.bold: true; font.letterSpacing: 1.2 }
                        Label { text: appBridge.connectionState; color: "#e8edf7"; font.pixelSize: 11; wrapMode: Text.WordWrap }
                    }
                }
                Label { text: appBridge.versionLabel; color: "#64748b"; font.pixelSize: 10 }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 16

            RowLayout {
                Layout.fillWidth: true
                ColumnLayout {
                    spacing: 3
                    Label { text: "Your downloads"; color: "white"; font.pixelSize: 27; font.bold: true }
                    Label { text: "Everything you download, beautifully organized."; color: muted; font.pixelSize: 12 }
                }
                Item { Layout.fillWidth: true }
                Rectangle {
                    radius: 13
                    color: "#1bffffff"
                    border.color: "#30ffffff"
                    Layout.preferredWidth: 190
                    Layout.preferredHeight: 42
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 11
                        Label { text: "⌕"; color: "#91a0b8"; font.pixelSize: 18 }
                        Label { text: "Search downloads"; color: "#91a0b8"; font.pixelSize: 11 }
                    }
                }
                Rectangle {
                    width: 42; height: 42; radius: 13
                    color: "#1bffffff"; border.color: "#30ffffff"
                    Label { anchors.centerIn: parent; text: "⚙"; color: "#dbe5f4"; font.pixelSize: 18 }
                }
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 3
                columnSpacing: 12
                rowSpacing: 12

                Repeater {
                    model: [
                        { title: "Active downloads", value: appBridge.activeDownloads.toString(), note: "Live engine data", tint: "#70ddc8" },
                        { title: "Download speed", value: appBridge.totalSpeed, note: "Combined transfer speed", tint: "#81a9ff" },
                        { title: "Completed today", value: appBridge.completedDownloads.toString(), note: "Completed downloads", tint: "#c19cff" }
                    ]
                    delegate: Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 112
                        radius: 18
                        color: "#a51a2943"
                        border.color: "#30ffffff"
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 15
                            spacing: 5
                            Label { text: modelData.title; color: muted; font.pixelSize: 11 }
                            Label { text: modelData.value; color: "white"; font.pixelSize: 25; font.bold: true }
                            Label { text: modelData.note; color: modelData.tint; font.pixelSize: 10 }
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 20
                color: "#a516243b"
                border.color: "#35ffffff"

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 20
                    spacing: 13
                    RowLayout {
                        Label { text: "Recent activity"; color: "white"; font.pixelSize: 17; font.bold: true }
                        Item { Layout.fillWidth: true }
                        Label { text: "PREVIEW"; color: "#70ddc8"; font.pixelSize: 9; font.bold: true; font.letterSpacing: 1.3 }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: "#22ffffff" }
                    ListView {
                        id: downloadList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 8
                        model: appBridge.downloadModel
                        delegate: Rectangle {
                            width: downloadList.width
                            height: 66
                            radius: 12
                            color: "#1bffffff"
                            border.color: "#20ffffff"
                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 12
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 3
                                    Label { text: fileName; color: "#e5edf8"; font.pixelSize: 12; elide: Text.ElideMiddle; Layout.fillWidth: true }
                                    Label { text: status + "  ·  " + speed; color: muted; font.pixelSize: 10 }
                                }
                                Label { text: progress + "%"; color: "#70ddc8"; font.pixelSize: 12; font.bold: true }
                            }
                        }
                        Label {
                            anchors.centerIn: parent
                            visible: downloadList.count === 0
                            width: parent.width - 24
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                            text: "The QML download list is ready for the backend adapter.\nNo live downloads are connected in this preview."
                            color: muted
                            font.pixelSize: 12
                        }
                    }
                }
            }
        }
    }
}
