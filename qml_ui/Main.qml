// CI validation branch marker: keep this interface buildable as a standalone Windows preview.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects

ApplicationWindow {
    id: window
    width: 1320
    height: 840
    minimumWidth: 1040
    minimumHeight: 700
    visible: true
    title: "ADM — All Download Manager"
    color: "#080e19"

    property color ink: "#f3f7ff"
    property color muted: "#91a0b7"
    property color dim: "#65758f"
    property color accent: "#6ce3cf"
    property color blue: "#7da7ff"
    property color surface: "#b817263c"
    property color line: "#2affffff"
    property string selectedSection: "Overview"
    property string searchText: ""
    property string actionMessage: ""
    property string scheduleTaskId: ""
    property string scheduleDraft: ""

    function sectionMatches(row) {
        return selectedSection === "Overview" || selectedSection === "All downloads"
            || (selectedSection === "In progress" && ["Downloading", "Checking server", "Retrying", "Checking metadata", "Seeding", "Connecting", "Starting", "Preparing", "Paused", "Canceling"].indexOf(row.status) >= 0)
            || (selectedSection === "Completed" && row.status === "Completed")
            || (selectedSection === "Scheduler" && row.scheduled_at.length > 0)
            || (selectedSection === "Queue" && row.status === "Queued")
            || (selectedSection === "Failed" && (row.status === "Failed" || row.status === "Canceled"))
    }

    function submitDownload() {
        const value = downloadUrlField.text.trim()
        if (!value.length)
            return
        appBridge.queueDownload(value, scheduleInput.text.trim())
        downloadUrlField.clear()
        scheduleInput.clear()
        downloadUrlField.forceActiveFocus()
    }

    function sectionCount(section) {
        if (section === "Overview" || section === "All downloads") return appBridge.downloads.length
        if (section === "In progress") return appBridge.activeDownloads
        if (section === "Completed") return appBridge.completedDownloads
        if (section === "Scheduler") return appBridge.scheduledDownloads
        if (section === "Queue") return appBridge.queuedDownloads
        if (section === "Failed") return appBridge.downloads.filter(row => row.status === "Failed" || row.status === "Canceled").length
        return appBridge.history.length
    }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#111d32" }
            GradientStop { position: 0.46; color: "#0b1424" }
            GradientStop { position: 1.0; color: "#080e19" }
        }
    }
    Rectangle {
        width: 600; height: 600; radius: 300
        x: parent.width - width * 0.62; y: -height * 0.48
        color: "#3978d8"; opacity: 0.12
        layer.enabled: true
        layer.effect: MultiEffect { blurEnabled: true; blur: 1.0 }
    }
    Rectangle {
        width: 480; height: 480; radius: 240
        x: -width * 0.62; y: parent.height - height * 0.55
        color: "#22c8a8"; opacity: 0.08
        layer.enabled: true
        layer.effect: MultiEffect { blurEnabled: true; blur: 1.0 }
    }

    component GlassPanel: Rectangle {
        color: surface
        radius: 20
        border.width: 1
        border.color: line
    }

    component NavItem: Rectangle {
        property string caption
        property string glyph
        property bool active: false
        property string badgeText: ""
        signal chosen()
        Layout.fillWidth: true
        height: 43
        radius: 12
        color: active ? "#3267d7c8" : navMouse.containsMouse ? "#18ffffff" : "transparent"
        border.color: active ? "#4b79e4d2" : "transparent"
        Behavior on color { ColorAnimation { duration: 150 } }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 10
            spacing: 12
            Label {
                text: glyph
                color: active ? accent : "#a5b4ca"
                font.pixelSize: 17
                Layout.preferredWidth: 20
                horizontalAlignment: Text.AlignHCenter
            }
            Label {
                text: caption
                color: active ? ink : "#b5c1d3"
                font.pixelSize: 12
                font.weight: active ? Font.DemiBold : Font.Normal
                Layout.fillWidth: true
            }
            Label {
                visible: badgeText.length > 0
                text: badgeText
                color: active ? "#d8fff8" : muted
                font.pixelSize: 10
            }
        }
        MouseArea { id: navMouse; anchors.fill: parent; hoverEnabled: true; onClicked: chosen() }
    }

    component ActionButton: Button {
        property color tint: "#6ce3cf"
        implicitHeight: 34
        contentItem: Label {
            text: parent.text
            color: parent.enabled ? (parent.highlighted ? "#07151d" : ink) : "#607087"
            font.pixelSize: 11
            font.weight: Font.DemiBold
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 10
            color: parent.highlighted ? parent.tint : (parent.hovered ? "#2bffffff" : "#16ffffff")
            border.width: 1
            border.color: parent.highlighted ? parent.tint : "#35ffffff"
        }
    }

    Dialog {
        id: settingsDialog
        title: "Download settings"
        modal: true
        anchors.centerIn: parent
        width: 470
        standardButtons: Dialog.Ok
        background: GlassPanel { color: "#f018263c"; radius: 18 }
        contentItem: ColumnLayout {
            spacing: 13
            Repeater {
                model: [
                    { label: "Maximum downloads", value: appBridge.settings.maxDownloads },
                    { label: "Connections per download", value: appBridge.settings.connectionsPerDownload },
                    { label: "Speed limit (KB/s)", value: appBridge.settings.speedLimitKbps },
                    { label: "Torrent upload limit (KB/s)", value: appBridge.settings.torrentUploadLimitKbps },
                    { label: "Proxy enabled", value: appBridge.settings.proxyEnabled },
                    { label: "Download folder", value: appBridge.settings.downloadFolder }
                ]
                delegate: RowLayout {
                    Layout.fillWidth: true
                    Label { text: modelData.label; color: muted; font.pixelSize: 11; Layout.fillWidth: true }
                    Label { text: modelData.value === null || modelData.value === undefined ? "Unavailable" : String(modelData.value); color: ink; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.maximumWidth: 220 }
                }
            }
            Label { text: "These values are read from the existing ADM engine. Editing will be enabled after settings validation is complete."; color: dim; font.pixelSize: 10; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        }
    }

    Dialog {
        id: scheduleDialog
        title: "Schedule download"
        modal: true
        anchors.centerIn: parent
        width: 440
        background: GlassPanel { color: "#f018263c"; radius: 18 }
        contentItem: ColumnLayout {
            spacing: 12
            Label { text: "Choose a future local date and time. Use ISO format."; color: muted; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            TextField {
                Layout.fillWidth: true
                text: window.scheduleDraft
                placeholderText: "YYYY-MM-DDTHH:MM:SS"
                color: ink
                selectByMouse: true
                background: Rectangle { radius: 10; color: "#27101b30"; border.color: "#40536c8d" }
                onTextChanged: window.scheduleDraft = text
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                ActionButton { text: "Cancel"; onClicked: scheduleDialog.close() }
                ActionButton { text: "Save schedule"; highlighted: true; onClicked: { appBridge.setSchedule(window.scheduleTaskId, window.scheduleDraft); scheduleDialog.close() } }
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 16

        GlassPanel {
            Layout.preferredWidth: 232
            Layout.fillHeight: true
            radius: 22
            color: "#bd111d30"
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 14
                RowLayout {
                    spacing: 11
                    Rectangle {
                        width: 43; height: 43; radius: 14
                        gradient: Gradient {
                            GradientStop { position: 0; color: "#83f1d9" }
                            GradientStop { position: 1; color: "#5797f4" }
                        }
                        Text { anchors.centerIn: parent; text: "A"; color: "#071522"; font.pixelSize: 25; font.bold: true }
                    }
                    ColumnLayout {
                        spacing: 0
                        Label { text: "ADM"; color: ink; font.pixelSize: 21; font.bold: true; letterSpacing: 1.1 }
                        Label { text: "ALL DOWNLOAD MANAGER"; color: "#8c9db7"; font.pixelSize: 8; font.letterSpacing: 1.2 }
                    }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: "#24ffffff" }
                Label { text: "WORKSPACE"; color: "#71839f"; font.pixelSize: 9; font.bold: true; font.letterSpacing: 1.6; leftPadding: 5 }
                NavItem { caption: "Overview"; glyph: "⌂"; active: selectedSection === caption; onChosen: selectedSection = caption }
                NavItem { caption: "All downloads"; glyph: "⇩"; badgeText: String(appBridge.downloads.length); active: selectedSection === caption; onChosen: selectedSection = caption }
                NavItem { caption: "In progress"; glyph: "◌"; badgeText: String(appBridge.activeDownloads); active: selectedSection === caption; onChosen: selectedSection = caption }
                NavItem { caption: "Completed"; glyph: "✓"; active: selectedSection === caption; onChosen: selectedSection = caption }
                NavItem { caption: "Scheduler"; glyph: "◷"; badgeText: String(appBridge.scheduledDownloads); active: selectedSection === caption; onChosen: selectedSection = caption }
                NavItem { caption: "Queue"; glyph: "☷"; badgeText: String(appBridge.queuedDownloads); active: selectedSection === caption; onChosen: selectedSection = caption }
                NavItem { caption: "Failed"; glyph: "!"; active: selectedSection === caption; onChosen: selectedSection = caption }
                NavItem { caption: "History"; glyph: "↺"; active: selectedSection === caption; onChosen: selectedSection = caption }
                Item { Layout.fillHeight: true }
                GlassPanel {
                    Layout.fillWidth: true
                    height: 90
                    radius: 15
                    color: "#251c2c43"
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 5
                        RowLayout {
                            Label { text: "ENGINE"; color: "#8294ae"; font.pixelSize: 9; font.bold: true; font.letterSpacing: 1.3 }
                            Item { Layout.fillWidth: true }
                            Rectangle { width: 7; height: 7; radius: 4; color: "#6ce3cf" }
                            Label { text: "CONNECTED"; color: "#8cebd8"; font.pixelSize: 8; font.bold: true }
                        }
                        Label { text: appBridge.connectionState; color: "#d2dbea"; font.pixelSize: 10; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                }
                RowLayout {
                    Label { text: appBridge.versionLabel; color: "#70809a"; font.pixelSize: 9 }
                    Item { Layout.fillWidth: true }
                    Label { text: "QML EDITION"; color: "#6e88aa"; font.pixelSize: 8; font.letterSpacing: 1 }
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 15

            RowLayout {
                Layout.fillWidth: true
                ColumnLayout {
                    spacing: 3
                    Label { text: selectedSection === "Overview" ? "Your downloads" : selectedSection; color: ink; font.pixelSize: 27; font.weight: Font.DemiBold }
                    Label { text: selectedSection === "Overview" ? "Everything in one place. Fast, clear, under control." : "Manage and monitor your transfers."; color: muted; font.pixelSize: 11 }
                }
                Item { Layout.fillWidth: true }
                Rectangle {
                    Layout.preferredWidth: 220
                    Layout.preferredHeight: 40
                    radius: 12
                    color: "#251b2b40"
                    border.color: line
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 11; anchors.rightMargin: 10; spacing: 8
                        Label { text: "⌕"; color: muted; font.pixelSize: 18 }
                        TextField {
                            id: searchField
                            Layout.fillWidth: true
                            placeholderText: "Search downloads"
                            color: ink
                            font.pixelSize: 11
                            background: Item {}
                            onTextChanged: searchText = text
                        }
                    }
                }
                Rectangle {
                    width: 40; height: 40; radius: 12
                    color: "#251b2b40"; border.color: line
                    Label { anchors.centerIn: parent; text: "⚙"; color: "#dbe5f4"; font.pixelSize: 17 }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: settingsDialog.open() }
                }
            }

            GlassPanel {
                Layout.fillWidth: true
                Layout.preferredHeight: 86
                radius: 18
                color: "#bf172b43"
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 12
                    Rectangle {
                        width: 44; height: 44; radius: 14
                        color: "#2b6ce3cf"
                        Label { anchors.centerIn: parent; text: "↓"; color: accent; font.pixelSize: 24; font.bold: true }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        Label { text: "Add a new download"; color: ink; font.pixelSize: 12; font.bold: true }
                        TextField {
                            id: downloadUrlField
                            Layout.fillWidth: true
                            placeholderText: "Paste a file URL, YouTube link or magnet link…"
                            color: ink
                            selectByMouse: true
                            font.pixelSize: 11
                            onAccepted: window.submitDownload()
                            background: Rectangle { radius: 9; color: "#29101b30"; border.color: "#33445f7e" }
                        }
                    }
                    ColumnLayout {
                        spacing: 3
                        Label { text: "START LATER (OPTIONAL)"; color: dim; font.pixelSize: 8; font.bold: true; letterSpacing: 0.7 }
                        TextField {
                            id: scheduleInput
                            Layout.preferredWidth: 190
                            placeholderText: "YYYY-MM-DDTHH:MM"
                            color: ink
                            font.pixelSize: 10
                            selectByMouse: true
                            background: Rectangle { radius: 9; color: "#29101b30"; border.color: "#33445f7e" }
                        }
                    }
                    ActionButton { text: "Add download"; highlighted: true; tint: "#75e6d1"; onClicked: window.submitDownload() }
                }
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 3
                columnSpacing: 12
                rowSpacing: 10
                Repeater {
                    model: [
                        { title: "ACTIVE DOWNLOADS", value: appBridge.activeDownloads.toString(), note: "Currently transferring", glyph: "⇩", tint: "#6ce3cf" },
                        { title: "TOTAL SPEED", value: appBridge.totalSpeed, note: "Combined transfer rate", glyph: "ϟ", tint: "#82aaff" },
                        { title: "COMPLETED", value: appBridge.completedDownloads.toString(), note: "Successfully downloaded", glyph: "✓", tint: "#c4a0ff" }
                    ]
                    delegate: GlassPanel {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 96
                        radius: 16
                        color: "#9f192940"
                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 12
                            Rectangle {
                                width: 38; height: 38; radius: 12
                                color: "#243d5b76"
                                Label { anchors.centerIn: parent; text: modelData.glyph; color: modelData.tint; font.pixelSize: 18; font.bold: true }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Label { text: modelData.title; color: muted; font.pixelSize: 8; font.bold: true; font.letterSpacing: 1.0 }
                                Label { text: modelData.value; color: ink; font.pixelSize: 23; font.bold: true }
                                Label { text: modelData.note; color: dim; font.pixelSize: 9 }
                            }
                        }
                    }
                }
            }

            GlassPanel {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 20
                color: "#a9142238"
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 17
                    spacing: 12
                    RowLayout {
                        Label { text: selectedSection === "History" ? "Download history" : selectedSection === "Scheduler" ? "Scheduled downloads" : "Transfer activity"; color: ink; font.pixelSize: 15; font.bold: true }
                        Item { Layout.fillWidth: true }
                        Label { text: String(sectionCount(selectedSection)) + " ITEMS"; color: dim; font.pixelSize: 9; font.bold: true; font.letterSpacing: 1.1 }
                        Rectangle { width: 6; height: 6; radius: 3; color: accent }
                        Label { text: "LIVE"; color: "#8cebd8"; font.pixelSize: 8; font.bold: true; font.letterSpacing: 1.2 }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: "#20ffffff" }
                    ListView {
                        id: downloadList
                        visible: selectedSection !== "History"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 8
                        model: appBridge.downloadModel
                        delegate: GlassPanel {
                            property bool matchesSection: window.sectionMatches({ status: status, scheduled_at: scheduledAt })
                            property bool matchesSearch: window.searchText.length === 0 || fileName.toLowerCase().indexOf(window.searchText.toLowerCase()) >= 0
                            visible: matchesSection && matchesSearch
                            width: downloadList.width
                            height: visible ? 88 : 0
                            radius: 13
                            color: "#281c2c43"
                            border.color: "#20ffffff"
                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 12
                                Rectangle {
                                    width: 38; height: 38; radius: 11
                                    color: status === "Completed" ? "#253ac9a8" : status === "Failed" ? "#2cdd7777" : "#293b6eb0"
                                    Label { anchors.centerIn: parent; text: status === "Completed" ? "✓" : status === "Failed" ? "!" : status === "Paused" ? "Ⅱ" : "↓"; color: status === "Completed" ? "#7ce8c9" : status === "Failed" ? "#ffaaaa" : "#9abaff"; font.pixelSize: 17; font.bold: true }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 5
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Label { text: fileName; color: ink; font.pixelSize: 11; font.bold: true; elide: Text.ElideMiddle; Layout.fillWidth: true }
                                        Label { text: progress + "%"; color: accent; font.pixelSize: 11; font.bold: true }
                                    }
                                    ProgressBar {
                                        Layout.fillWidth: true
                                        implicitHeight: 5
                                        from: 0; to: 100; value: progress
                                        background: Rectangle { radius: 3; color: "#33445670" }
                                        contentItem: Item {
                                            Rectangle { width: parent.width * progress / 100; height: parent.height; radius: 3; gradient: Gradient { GradientStop { position: 0; color: "#65d9c5" } GradientStop { position: 1; color: "#6d9df4" } } }
                                        }
                                    }
                                    Label { text: status + "   ·   " + speed + (category.length ? "   ·   " + category : "") + (scheduledAt.length ? "   ·   Starts " + scheduledAt : ""); color: muted; font.pixelSize: 9; elide: Text.ElideRight; Layout.fillWidth: true }
                                }
                                ToolButton {
                                    text: status === "Paused" ? "▶" : "Ⅱ"
                                    enabled: status === "Paused" || ["Downloading", "Checking server", "Retrying", "Checking metadata", "Seeding"].indexOf(status) >= 0
                                    onClicked: status === "Paused" ? appBridge.resume(downloadId) : appBridge.pause(downloadId)
                                }
                                ToolButton { text: "×"; enabled: !["Completed", "Canceled", "Failed", "Canceling"].includes(status); onClicked: appBridge.cancel(downloadId) }
                                ToolButton { text: "↻"; enabled: status === "Failed" || status === "Canceled"; onClicked: appBridge.retry(downloadId) }
                                ToolButton {
                                    text: "◷"
                                    visible: status === "Queued"
                                    onClicked: { window.scheduleTaskId = downloadId; window.scheduleDraft = scheduledAt; scheduleDialog.open() }
                                }
                                ToolButton { text: "Now"; visible: scheduledAt.length > 0 && status === "Queued"; onClicked: appBridge.startNow(downloadId) }
                                ToolButton { text: "Clear"; visible: scheduledAt.length > 0; onClicked: appBridge.clearSchedule(downloadId) }
                            }
                        }
                        Label {
                            anchors.centerIn: parent
                            visible: selectedSection !== "History" && appBridge.downloads.filter(row => window.sectionMatches(row) && (window.searchText.length === 0 || row.file_name.toLowerCase().indexOf(window.searchText.toLowerCase()) >= 0)).length === 0
                            width: parent.width - 30
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                            text: appBridge.downloads.length === 0 ? "No downloads yet. Paste a link above to get started." : "Nothing matches this view."
                            color: muted
                            font.pixelSize: 11
                        }
                    }
                    ListView {
                        id: historyList
                        visible: selectedSection === "History"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 8
                        model: appBridge.history
                        delegate: GlassPanel {
                            width: historyList.width
                            visible: window.searchText.length === 0 || modelData.file_name.toLowerCase().indexOf(window.searchText.toLowerCase()) >= 0
                            height: visible ? (modelData.error.length > 0 ? 76 : 62) : 0
                            radius: 12
                            color: "#281c2c43"
                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 12
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 4
                                    Label { text: modelData.file_name; color: ink; font.pixelSize: 11; font.bold: true; elide: Text.ElideMiddle; Layout.fillWidth: true }
                                    Label { text: modelData.status + (modelData.time.length ? "   ·   " + modelData.time : ""); color: muted; font.pixelSize: 9 }
                                    Label { visible: modelData.error.length > 0; text: modelData.error; color: "#f1a5a5"; font.pixelSize: 9; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                }
                                Label { text: modelData.size.toLocaleString() + " bytes"; color: accent; font.pixelSize: 10 }
                            }
                        }
                        Label {
                            anchors.centerIn: parent
                            visible: appBridge.history.filter(item => window.searchText.length === 0 || item.file_name.toLowerCase().indexOf(window.searchText.toLowerCase()) >= 0).length === 0
                            text: appBridge.history.length === 0 ? "No download history yet." : "No history items match your search."
                            color: muted
                            font.pixelSize: 11
                        }
                    }
                }
            }
        }
    }

    Connections {
        target: appBridge
        function onActionRejected(message) {
            window.actionMessage = message
            actionToast.restart()
        }
    }
    Timer {
        id: actionToast
        interval: 4000
        repeat: false
        onTriggered: window.actionMessage = ""
    }
    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 24
        z: 30
        visible: window.actionMessage.length > 0
        radius: 12
        color: "#ed26354a"
        border.color: "#687fe3cf"
        width: Math.min(parent.width - 48, toastLabel.implicitWidth + 38)
        height: toastLabel.implicitHeight + 22
        Label {
            id: toastLabel
            anchors.centerIn: parent
            width: parent.width - 26
            text: window.actionMessage
            color: ink
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            font.pixelSize: 11
        }
    }
}
